# Data dictionary

## Provenance

56 official daily ZIP archives: two USD-M perpetual instruments, fourteen UTC
days, two stream types. SHA-256 is verified against each provider `.CHECKSUM`.
The URL, size, checksum and resulting per-day audit are in `data/audit/`.
Only noncommercial historical research is implemented.

## Processed observations

One row per symbol at each integer UTC second. Columns:

| Column | Meaning |
| --- | --- |
| `second` | Epoch second at the **end** of the latest aggregation interval |
| `symbol` | BTCUSDT or ETHUSDT USD-M perpetual contract |
| `bid`, `ask` | Last observed best bid/ask published at or before the boundary; USDT per base unit |
| `bid_qty`, `ask_qty` | Base-asset quantity at the displayed best prices |
| `quote_age_ms` | Boundary time minus last quote publication time; milliseconds |
| `ofi` | Sum of observed BBO OFI contributions in `(t-1s,t]`; base units |
| `quote_updates` | Count of accepted BBO records in `(t-1s,t]` |
| `trade_qty` | Aggregate traded base quantity assumed available in `(t-1s,t]` |
| `signed_trade_qty` | Buy-aggressor quantity minus sell-aggressor quantity |
| `trade_count` | Number of aggregate-trade records, not necessarily individual executions |

Book `event_time` is an exchange publication proxy. Trade availability is assumed
to be `transact_time + 1000 ms`; this is not an observed network arrival time.
All equal-time book updates are retained in source/update order. The initial
book observation contributes zero OFI because no preceding state is available.

No quote is backfilled. Last quotes can be carried within a day to preserve a
grid, but research rejects current and target endpoints older than 1000 ms.
The first 60 seconds are warmup. Trailing feature gaps are median-imputed using
training-only statistics. Neither labels nor quote state are carried overnight.

## Source disorder

BTCUSDT 2024-01-02 contains interleaved chronological segments. An attempted
streaming filter was rejected at audit before model fitting. The final pipeline
uses an external disk-backed sort by `event_time, update_id` and exact-row
deduplication before calculating OFI. In this file, **zero exact duplicates**
were removed: all 18,518,655 records were preserved. Other archives were already
ordered under the validation rule. Quality checks fail instead of silently
discarding a disordered stream.

## Research units

Returns and predicted changes are simple midpoint returns in basis points:
`10000 * (future_mid / current_mid - 1)`. MSE is in squared basis points.
`r2_vs_zero` equals `1 - MSE / mean(target**2)`, not centered test-mean R².
Direction accuracy includes only nonzero target returns; sample counts are
included. All target horizons and economic delays use seconds.

## Scope

This is observed **top-of-book** flow, not a full order-level reconstruction.
Changes cannot separately identify all market orders, limit orders, cancellations
or hidden liquidity. No fill probability or queue position is estimated.

## Final review: timing and complete-case limitations

Freshness is measured from **book publication time**, not the underlying
transaction time. Audits contain training publication backlogs up to 128 seconds
and a sampled BTC p99 delay of about 5.32 seconds on January 9. These records
remain eligible once published; predictions may partly reflect feed catch-up.
Test-period sampled p99 delays are mostly 14-28 ms, with individual maxima
around 1.1-2.9 seconds. The trade-availability lag is assumed, not measured,
and cannot establish cross-stream availability during backlogs. A future
independent study should explicitly model or filter transaction-age as well.

The economic scenarios are **complete-case diagnostics**: selection requires a
valid future one-second label and each scenario requires available future exit
quotes. Missing future outcomes are excluded. This is not an ex-ante executable
strategy; a proper execution simulation would keep every decision and account
for unpriced/failed exits. No profitable or deployable strategy is claimed.

The factor is observed BBO-update imbalance (a Cont-style OFI proxy). Individual
bookTicker streams are documented as real-time best-price/size updates, but
archive completeness and full order-level events are not established.
