"""Verified public archive acquisition and bounded-memory causal aggregation.

Every grid point t observes events in (t-1s, t]. BBO records retain their
within-millisecond file order. Event time is an exchange publication proxy,
not a measured local receipt timestamp. Trades are assigned an explicit
1,000 ms assumed availability lag, configurable before running a study.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE = "https://data.binance.vision/data/futures/um/daily"
BOOK_COLUMNS = ["update_id", "best_bid_price", "best_bid_qty", "best_ask_price", "best_ask_qty", "transaction_time", "event_time"]


class UnorderedArchive(ValueError):
    """Requires canonical ordering before any feature aggregation."""


def book_chunks(path: Path, chunk_size):
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq
        for batch in pq.ParquetFile(path).iter_batches(batch_size=chunk_size):
            yield batch.to_pandas()
    else:
        with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as f:
            yield from pd.read_csv(f, usecols=BOOK_COLUMNS, chunksize=chunk_size)


def sort_book_archive(path: Path, destination: Path) -> dict:
    """Disk-backed ordering and exact-row deduplication, with an audit trail."""
    import duckdb
    destination.parent.mkdir(parents=True, exist_ok=True)
    csv = destination.with_suffix(".csv")
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as src, csv.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    def sql_quote(value):
        return "'" + str(value).replace("'", "''") + "'"
    con = duckdb.connect()
    con.execute("SET memory_limit='1GB'")
    con.execute(f"SET temp_directory={sql_quote(destination.parent / 'duckdb-spill')}")
    con.execute("SET threads=2")
    source = f"read_csv({sql_quote(csv)}, header=true)"
    total = con.execute(f"SELECT count(*) FROM {source}").fetchone()[0]
    con.execute(f"COPY (SELECT DISTINCT * FROM {source} ORDER BY event_time, update_id) TO {sql_quote(destination)} (FORMAT PARQUET)")
    unique = con.execute(f"SELECT count(*) FROM read_parquet({sql_quote(destination)})").fetchone()[0]
    con.close()
    csv.unlink()
    return {"reordered_before_aggregation": True, "source_rows_before_exact_dedup": total,
            "exact_duplicate_rows_removed": total - unique,
            "canonical_order": "event_time, update_id; exact duplicate rows removed"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def fetch_archive(symbol: str, day: str, kind: str, raw_dir: Path) -> tuple[Path, dict]:
    """Download using system CA trust via curl; fail on HTTP/checksum errors."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    name = f"{symbol}-{kind}-{day}.zip"
    url = f"{BASE}/{kind}/{symbol}/{name}"
    path, checksum = raw_dir / name, raw_dir / (name + ".CHECKSUM")
    if not checksum.exists():
        subprocess.run(["curl", "--fail", "--silent", "--show-error", "--retry", "3", "--max-time", "120", url + ".CHECKSUM", "-o", str(checksum)], check=True)
    expected = checksum.read_text().split()[0]
    if len(expected) != 64:
        raise ValueError(f"Invalid vendor checksum: {checksum}")
    if not path.exists():
        partial = path.with_suffix(".zip.partial")
        subprocess.run(["curl", "--fail", "--silent", "--show-error", "--retry", "3", "--max-time", "600", url, "-o", str(partial)], check=True)
        partial.rename(path)
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"Checksum mismatch for {name}; remove the bad archive before retry")
    return path, {"url": url, "file": name, "sha256": actual, "bytes": path.stat().st_size, "checksum_verified": True}


def ofi_events(bid, bid_qty, ask, ask_qty, previous=None):
    """Cont-style BBO update imbalance; first ever observation contributes zero."""
    bid, bid_qty, ask, ask_qty = map(np.asarray, (bid, bid_qty, ask, ask_qty))
    if len(bid) == 0:
        return np.array([], dtype=float)
    prev = previous if previous is not None else (bid[0], bid_qty[0], ask[0], ask_qty[0])
    pb = np.r_[prev[0], bid[:-1]]
    pqb = np.r_[prev[1], bid_qty[:-1]]
    pa = np.r_[prev[2], ask[:-1]]
    pqa = np.r_[prev[3], ask_qty[:-1]]
    return ((bid >= pb) * bid_qty - (bid <= pb) * pqb
            - (ask <= pa) * ask_qty + (ask >= pa) * pqa)


def grid_bin(timestamp_ms, start_ms):
    """Ceiling to boundary: a record at 1,001 ms is first known at 2 s."""
    return (np.asarray(timestamp_ms, dtype=np.int64) - start_ms + 999) // 1000


def ordered_mask(times, ids, last_time=-1, last_id=-1):
    """Keep records ordered after the last accepted record, across chunks.

    A rejected record cannot advance either watermark. The normal ordered
    feed takes a vectorized fast path; only anomalous chunks require a scan.
    """
    times, ids = np.asarray(times), np.asarray(ids)
    if not len(times):
        return np.empty(0, dtype=bool)
    if (times[0] >= last_time and ids[0] > last_id
            and np.all(times[1:] >= times[:-1])
            and np.all(ids[1:] > ids[:-1])):
        return np.ones(len(times), dtype=bool)
    keep = np.zeros(len(times), dtype=bool)
    for i, (timestamp, update_id) in enumerate(zip(times, ids)):
        if timestamp >= last_time and update_id > last_id:
            keep[i] = True
            last_time, last_id = timestamp, update_id
    return keep


def aggregate_day(book_path: Path, trade_path: Path, symbol: str, day: str, trade_lag_ms=1000, chunk_size=500_000):
    start_ms = int(pd.Timestamp(day, tz="UTC").timestamp() * 1000)
    n = 86_400
    arrays = {key: np.full(n, np.nan) for key in ("bid", "ask", "bid_qty", "ask_qty", "last_event_ms")}
    sums = {key: np.zeros(n, dtype=float) for key in ("ofi", "quote_updates", "trade_qty", "signed_trade_qty", "trade_count")}
    audit = {"symbol": symbol, "date": day, "book_rows": 0, "book_rejected": 0, "out_of_order_or_duplicate": 0, "trade_rows": 0, "trade_rejected": 0, "publication_delay_max_ms": 0}
    previous, last_time, last_id = None, -1, -1
    delay_samples = []
    for chunk in book_chunks(book_path, chunk_size):
        audit["book_rows"] += len(chunk)
        valid = ((chunk.best_bid_price > 0) & (chunk.best_ask_price > chunk.best_bid_price) & (chunk.best_bid_qty > 0) & (chunk.best_ask_qty > 0) & (chunk.event_time >= chunk.transaction_time))
        audit["book_rejected"] += int((~valid).sum())
        c = chunk.loc[valid]
        if c.empty:
            continue
        times = c.event_time.to_numpy(np.int64)
        ids = c.update_id.to_numpy(np.int64)
        ordered = ordered_mask(times, ids, last_time, last_id)
        if not ordered.all():
            raise UnorderedArchive(f"Nonchronological or duplicate updates in {book_path.name}; canonicalize source")
        audit["out_of_order_or_duplicate"] += int((~ordered).sum())
        c = c.loc[ordered]
        if c.empty:
            continue
        times, ids = c.event_time.to_numpy(np.int64), c.update_id.to_numpy(np.int64)
        b, qb, a, qa = (c[col].to_numpy(float) for col in ("best_bid_price", "best_bid_qty", "best_ask_price", "best_ask_qty"))
        flow = ofi_events(b, qb, a, qa, previous)
        previous = (b[-1], qb[-1], a[-1], qa[-1])
        last_time, last_id = int(times[-1]), int(ids[-1])
        delay = times - c.transaction_time.to_numpy(np.int64)
        audit["publication_delay_max_ms"] = max(audit["publication_delay_max_ms"], int(delay.max()))
        delay_samples.extend(delay[::1000].tolist())
        idx = grid_bin(times, start_ms)
        inside = (idx >= 0) & (idx < n)
        idx = idx[inside]
        if not len(idx):
            continue
        sums["ofi"] += np.bincount(idx, weights=flow[inside], minlength=n)
        sums["quote_updates"] += np.bincount(idx, minlength=n)
        # Final update at each boundary, preserving all OFI events before it.
        last = np.r_[np.flatnonzero(np.diff(idx)), len(idx) - 1]
        for key, val in (("bid", b), ("ask", a), ("bid_qty", qb), ("ask_qty", qa), ("last_event_ms", times)):
            arrays[key][idx[last]] = val[inside][last]
    last_trade_time, last_trade_id = -1, -1
    with zipfile.ZipFile(trade_path) as z:
        with z.open(z.namelist()[0]) as f:
            for c in pd.read_csv(f, chunksize=chunk_size):
                audit["trade_rows"] += len(c)
                valid = (c.quantity > 0) & (c.price > 0)
                audit["trade_rejected"] += int((~valid).sum())
                c = c.loc[valid]
                if c.empty:
                    continue
                t = c.transact_time.to_numpy(np.int64)
                tid = c.agg_trade_id.to_numpy(np.int64)
                ordered = ordered_mask(t, tid, last_trade_time, last_trade_id)
                if not ordered.all():
                    raise ValueError("Unordered or duplicate trades require source inspection")
                audit["trade_rejected"] += int((~ordered).sum())
                c = c.loc[ordered]
                if c.empty:
                    continue
                last_trade_time, last_trade_id = int(c.transact_time.iloc[-1]), int(c.agg_trade_id.iloc[-1])
                idx = grid_bin(c.transact_time.to_numpy(np.int64) + trade_lag_ms, start_ms)
                qty = c.quantity.to_numpy(float)
                maker = c.is_buyer_maker.astype(str).str.lower()
                if not maker.isin(["true", "false"]).all():
                    raise ValueError("Unrecognized maker flag")
                sign = np.where(maker.eq("true"), -1, 1)
                inside = (idx >= 0) & (idx < n)
                sums["trade_qty"] += np.bincount(idx[inside], weights=qty[inside], minlength=n)
                sums["signed_trade_qty"] += np.bincount(idx[inside], weights=(qty * sign)[inside], minlength=n)
                sums["trade_count"] += np.bincount(idx[inside], minlength=n)
    frame = pd.DataFrame(arrays).ffill()  # never fills backward or across UTC days
    frame["second"] = start_ms // 1000 + np.arange(n)
    frame["symbol"] = symbol
    frame["quote_age_ms"] = frame.second * 1000 - frame.pop("last_event_ms")
    for key, val in sums.items():
        frame[key] = val
    audit["grid_rows"] = n
    audit["fresh_quote_rows"] = int((frame.quote_age_ms <= 1000).sum())
    audit["missing_initial_quote_rows"] = int(frame.bid.isna().sum())
    audit["publication_delay_sample_p50_ms"] = float(np.median(delay_samples)) if delay_samples else None
    audit["publication_delay_sample_p99_ms"] = float(np.quantile(delay_samples, .99)) if delay_samples else None
    audit["trade_availability_lag_ms"] = trade_lag_ms
    return frame, audit


def prepare_data(root: Path, config: dict, workers=2):
    raw, processed = root / "data/raw", root / "data/processed"
    processed.mkdir(parents=True, exist_ok=True)
    audit_dir = root / "data/audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    start, end = date.fromisoformat(config["start_date"]), date.fromisoformat(config["end_date"])
    jobs = [(symbol, (start + timedelta(days=i)).isoformat()) for i in range((end-start).days + 1) for symbol in config["symbols"]]

    def one(symbol, day):
        output, audit_path = processed / f"{symbol}-{day}.parquet", audit_dir / f"{symbol}-{day}.json"
        if output.exists() and audit_path.exists():
            saved = json.loads(audit_path.read_text())
            if saved.get("trade_availability_lag_ms") != config["trade_availability_lag_ms"]:
                raise ValueError("Cached data lag differs from config; use a clean data directory")
            if saved.get("processed_sha256") != sha256(output):
                raise ValueError("Processed file checksum mismatch")
            return f"cached {symbol} {day}"
        book, book_meta = fetch_archive(symbol, day, "bookTicker", raw)
        trade, trade_meta = fetch_archive(symbol, day, "aggTrades", raw)
        sort_audit = {"reordered_before_aggregation": False, "exact_duplicate_rows_removed": 0}
        try:
            frame, audit = aggregate_day(book, trade, symbol, day, config["trade_availability_lag_ms"])
        except UnorderedArchive:
            canonical = root / "tmp/canonical" / f"{symbol}-{day}.parquet"
            print(f"Canonicalizing interleaved archive: {symbol} {day}", flush=True)
            sort_audit = sort_book_archive(book, canonical)
            frame, audit = aggregate_day(canonical, trade, symbol, day, config["trade_availability_lag_ms"])
        audit.update(sort_audit)
        frame.to_parquet(output, index=False)
        audit["sources"] = [book_meta, trade_meta]
        audit["processed_sha256"] = sha256(output)
        audit_path.write_text(json.dumps(audit, indent=2) + "\n")
        return f"prepared {symbol} {day}: {audit['book_rows']:,} quotes, {audit['trade_rows']:,} trades"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, *job) for job in jobs]
        for future in as_completed(futures):
            print(future.result(), flush=True)
    manifest = [json.loads((audit_dir / f"{s}-{d}.json").read_text()) for s, d in jobs]
    (audit_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
