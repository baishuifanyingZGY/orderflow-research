"""Causal order-flow research with a predeclared chronological evaluation.

This module consumes one-second observations constructed using data available at
the labelled second. It does not infer arrival times or reconstruct event-level
OFI from bar endpoints. All execution results are hypothetical quote-crossing
exercises, not realizable backtest P&L.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


CONTROL_FEATURES = ["return_1s_bps", "return_5s_bps", "spread_bps", "volatility_30s_bps"]
FLOW_FEATURES = CONTROL_FEATURES + [
    "queue_imbalance", "normalized_ofi_1s", "normalized_ofi_5s",
    "trade_imbalance_5s", "quote_intensity_5s", "trade_intensity_5s",
]
LIQUIDITY_FEATURES = FLOW_FEATURES + [
    "log_depth", "ofi_x_spread", "imbalance_x_spread",
    "ofi_x_volatility", "imbalance_x_volatility",
]
MODEL_FEATURES = {
    "zero": [], "ridge_control": CONTROL_FEATURES,
    "ridge_quote_only": [f for f in FLOW_FEATURES if f not in ("trade_imbalance_5s", "trade_intensity_5s")],
    "ridge_orderflow": FLOW_FEATURES,
    "ridge_liquidity": LIQUIDITY_FEATURES,
    "hist_gradient_boosting": LIQUIDITY_FEATURES,
}

DEFAULT_CONFIG: dict[str, Any] = {
    "seed": 1729,
    "train_dates": [f"2024-01-{day:02d}" for day in range(1, 8)],
    "validation_dates": [f"2024-01-{day:02d}" for day in range(8, 11)],
    "test_dates": [f"2024-01-{day:02d}" for day in range(11, 15)],
    "warmup_seconds": 60, "max_quote_age_ms": 1000,
    "train_stride_seconds": 5, "target_horizons_seconds": [1, 5, 10],
    "primary_horizon_seconds": 1, "ridge_alpha": 100.0,
    "hgb": {"max_iter": 100, "max_depth": 3, "max_leaf_nodes": 15,
            "l2_regularization": 10.0, "learning_rate": 0.05,
            "early_stopping": False},
    "bootstrap_repetitions": 5000, "signal_threshold_quantile": 0.90,
    "trade_grid_seconds": 10, "hold_seconds": 5,
    "entry_delays_seconds": [0, 1, 2], "fees_bps_per_side": [0.0, 1.0, 5.0],
}


def resolved_config(config: dict | None = None) -> dict:
    """Return a validated copy; changing settings creates a different protocol."""
    result = json.loads(json.dumps(DEFAULT_CONFIG))
    if config:
        unknown = set(config) - set(result)
        if unknown:
            raise ValueError(f"Unknown configuration keys: {sorted(unknown)}")
        for key, value in config.items():
            if key == "hgb":
                result[key].update(value)
            else:
                result[key] = value
    groups = [set(result[f"{s}_dates"]) for s in ("train", "validation", "test")]
    if any(not group for group in groups):
        raise ValueError("Each chronological partition must contain dates")
    if (groups[0] & groups[1]) or (groups[0] & groups[2]) or (groups[1] & groups[2]):
        raise ValueError("Train, validation, and test dates must be disjoint")
    if not max(groups[0]) < min(groups[1]) or not max(groups[1]) < min(groups[2]):
        raise ValueError("Partitions must be chronological")
    if result["primary_horizon_seconds"] not in result["target_horizons_seconds"]:
        raise ValueError("Primary horizon must be among target horizons")
    if min(result["entry_delays_seconds"]) < 0:
        raise ValueError("Entry delays cannot be negative")
    if max(result["entry_delays_seconds"]) + result["hold_seconds"] >= result["trade_grid_seconds"]:
        raise ValueError("Trade grid must exceed the latest possible exit offset")
    if result["warmup_seconds"] < 30 or result["train_stride_seconds"] < 1:
        raise ValueError("Warmup must cover volatility history and stride must be positive")
    return result


def build_features(observations: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    """Build strictly backward-looking features and within-day future labels.

    A file may contain more than one symbol/day. Missing seconds are inserted as
    unknown observations; quotes are never forward-filled. A stale current quote
    makes the row ineligible. Stale/missing target endpoint makes its label NaN.
    Incomplete trailing features remain NaN for train-fitted median imputation.
    """
    cfg = resolved_config(config)
    required = {"second", "symbol", "bid", "ask", "bid_qty", "ask_qty", "ofi",
                "quote_updates", "trade_qty", "signed_trade_qty", "trade_count", "quote_age_ms"}
    missing = required - set(observations)
    if missing:
        raise ValueError(f"Missing input columns: {sorted(missing)}")
    source = observations.copy()
    source["date"] = pd.to_datetime(source["second"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
    parts = []
    for (symbol, day), raw in source.groupby(["symbol", "date"], sort=True):
        if raw["second"].duplicated().any():
            raise ValueError(f"Duplicate seconds for {symbol} on {day}")
        raw = raw.sort_values("second").set_index("second")
        grid = pd.RangeIndex(int(raw.index.min()), int(raw.index.max()) + 1, name="second")
        raw = raw.reindex(grid)
        raw["symbol"] = symbol
        raw["date"] = day
        fresh = (raw["quote_age_ms"].between(0, cfg["max_quote_age_ms"]) &
                 (raw["bid"] > 0) & (raw["ask"] >= raw["bid"]) &
                 (raw["bid_qty"] > 0) & (raw["ask_qty"] > 0))
        mid = ((raw["bid"] + raw["ask"]) / 2).where(fresh)
        depth = (raw["bid_qty"] + raw["ask_qty"]).where(fresh)
        frame = raw[["symbol", "date", "bid", "ask", "quote_age_ms"]].copy()
        frame["quote_valid"] = fresh
        frame["mid"] = mid
        frame["depth"] = depth
        frame["warmup_complete"] = (frame.index - frame.index.min()) >= cfg["warmup_seconds"]
        frame["queue_imbalance"] = ((raw["bid_qty"] - raw["ask_qty"]) / depth).where(fresh)
        frame["normalized_ofi_1s"] = raw["ofi"] / depth
        frame["normalized_ofi_5s"] = raw["ofi"].rolling(5, min_periods=5).sum() / depth.rolling(5, min_periods=5).mean()
        frame["return_1s_bps"] = (mid / mid.shift(1) - 1) * 1e4
        frame["return_5s_bps"] = (mid / mid.shift(5) - 1) * 1e4
        frame["spread_bps"] = ((raw["ask"] - raw["bid"]) / mid) * 1e4
        frame["log_depth"] = np.log1p(depth)
        frame["volatility_30s_bps"] = frame["return_1s_bps"].rolling(30, min_periods=30).std(ddof=0)
        trade_total = raw["trade_qty"].rolling(5, min_periods=5).sum()
        trade_signed = raw["signed_trade_qty"].rolling(5, min_periods=5).sum()
        frame["trade_imbalance_5s"] = (trade_signed / trade_total).where(trade_total != 0, 0)
        frame["quote_intensity_5s"] = np.log1p(raw["quote_updates"].rolling(5, min_periods=5).sum())
        frame["trade_intensity_5s"] = np.log1p(raw["trade_count"].rolling(5, min_periods=5).sum())
        frame["ofi_x_spread"] = frame["normalized_ofi_5s"] * frame["spread_bps"]
        frame["imbalance_x_spread"] = frame["queue_imbalance"] * frame["spread_bps"]
        frame["ofi_x_volatility"] = frame["normalized_ofi_5s"] * frame["volatility_30s_bps"]
        frame["imbalance_x_volatility"] = frame["queue_imbalance"] * frame["volatility_30s_bps"]
        for horizon in cfg["target_horizons_seconds"]:
            frame[f"target_{horizon}s_bps"] = (mid.shift(-horizon) / mid - 1) * 1e4
        for name in LIQUIDITY_FEATURES:
            frame[name] = frame[name].replace([np.inf, -np.inf], np.nan).astype("float32")
        parts.append(frame.reset_index())
    if not parts:
        raise ValueError("No observations provided")
    return pd.concat(parts, ignore_index=True)


def assign_split(dates: pd.Series, config: dict | None = None) -> pd.Series:
    cfg = resolved_config(config)
    splits = pd.Series("excluded", index=dates.index, dtype="object")
    for split in ("train", "validation", "test"):
        splits.loc[dates.isin(cfg[f"{split}_dates"])] = split
    return splits


def regression_metrics(y: np.ndarray | pd.Series, prediction: np.ndarray | pd.Series) -> dict:
    y, prediction = np.asarray(y, dtype=float), np.asarray(prediction, dtype=float)
    finite = np.isfinite(y) & np.isfinite(prediction)
    y, prediction = y[finite], prediction[finite]
    if not len(y):
        return {key: None for key in ("n", "mse", "mae", "r2_vs_zero", "correlation", "directional_accuracy", "nonzero_target_count")}
    error = prediction - y
    mse = float(np.mean(error ** 2))
    denominator = float(np.mean(y ** 2))
    corr = float(np.corrcoef(y, prediction)[0, 1]) if np.std(y) > 0 and np.std(prediction) > 0 else None
    nonzero = y != 0
    return {"n": int(len(y)), "mse": mse, "mae": float(np.mean(np.abs(error))),
            "r2_vs_zero": 1 - mse / denominator if denominator else None,
            "correlation": corr,
            "directional_accuracy": float(np.mean(np.sign(prediction[nonzero]) == np.sign(y[nonzero]))) if nonzero.any() else None,
            "nonzero_target_count": int(nonzero.sum())}


def economic_exercise(quotes: pd.DataFrame, decisions: pd.DataFrame, threshold: float,
                      config: dict | None = None) -> pd.DataFrame:
    """Hypothetical ask/bid crossing, exact fresh quote endpoints, no fills assumed.

    Returns use decision-time midpoint as a common fixed-notional denominator,
    for both long and short. Fees are charged on entry and exit notional. The
    denominator avoids a favorable short-return artifact from using bid entry.
    No compounding, portfolio path, Sharpe ratio, or queue model is produced.
    """
    cfg = resolved_config(config)
    if len(decisions) == 0:
        return pd.DataFrame()
    required = ["symbol", "second", "date", "bid", "ask", "quote_valid"]
    q = quotes[required].drop_duplicates(["symbol", "second"]).copy()
    chosen = decisions.loc[(decisions["second"] % cfg["trade_grid_seconds"] == 0) &
                           (decisions["prediction"].abs() >= threshold) &
                           (decisions["prediction"] != 0)].copy()
    records = []
    for delay in cfg["entry_delays_seconds"]:
        selected = chosen.copy()
        selected["entry_second"] = selected["second"] + delay
        selected["exit_second"] = selected["entry_second"] + cfg["hold_seconds"]
        entry = q.rename(columns={"second": "entry_second", "date": "entry_date", "bid": "entry_bid", "ask": "entry_ask", "quote_valid": "entry_fresh"})
        leave = q.rename(columns={"second": "exit_second", "date": "exit_date", "bid": "exit_bid", "ask": "exit_ask", "quote_valid": "exit_fresh"})
        selected = selected.merge(entry, on=["symbol", "entry_second"], how="left", validate="many_to_one")
        selected = selected.merge(leave, on=["symbol", "exit_second"], how="left", validate="many_to_one")
        valid = ((selected["entry_fresh"] == True) & (selected["exit_fresh"] == True) &
                 (selected["date"] == selected["entry_date"]) & (selected["date"] == selected["exit_date"]))
        selected = selected.loc[valid].copy()
        if selected.empty:
            continue
        side = np.sign(selected["prediction"])
        selected["side"] = side.astype(int)
        selected["entry_price"] = np.where(side > 0, selected["entry_ask"], selected["entry_bid"])
        selected["exit_price"] = np.where(side > 0, selected["exit_bid"], selected["exit_ask"])
        selected["entry_delay_seconds"] = delay
        selected["gross_return_bps"] = side * (selected["exit_price"] - selected["entry_price"]) / selected["mid"] * 1e4
        fee_scale = (selected["entry_price"] + selected["exit_price"]) / selected["mid"]
        for fee in cfg["fees_bps_per_side"]:
            charged = selected.copy()
            charged["fee_bps_per_side"] = fee
            charged["net_return_bps"] = charged["gross_return_bps"] - fee * fee_scale
            records.append(charged[["symbol", "date", "second", "prediction", "side", "entry_second", "exit_second", "entry_delay_seconds", "fee_bps_per_side", "entry_price", "exit_price", "gross_return_bps", "net_return_bps"]])
    return pd.concat(records, ignore_index=True) if records else pd.DataFrame()


def _pipeline(name: str, cfg: dict) -> Pipeline:
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    if name == "hist_gradient_boosting":
        return Pipeline([("imputer", imputer), ("model", HistGradientBoostingRegressor(random_state=cfg["seed"], **cfg["hgb"]))])
    return Pipeline([("imputer", imputer), ("scaler", StandardScaler()),
                     ("model", Ridge(alpha=cfg["ridge_alpha"]))])


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.ndarray):
        return _safe_json(value.tolist())
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(_safe_json(value), indent=2, allow_nan=False) + "\n")


def run_research(processed_dir: str | Path, output_dir: str | Path, config: dict | None = None) -> dict:
    """Run the fixed protocol, save machine-readable artifacts, return summary.

    Model fitting occurs only on train rows. Validation chooses a model from the
    predeclared list and a 90th-percentile absolute-signal threshold. The same
    frozen model is evaluated on test without retraining or tuning. Calling this
    repeatedly after inspecting test results constitutes a new exploratory run.
    """
    cfg = resolved_config(config)
    processed_dir, output_dir = Path(processed_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "summary.json").exists():
        raise FileExistsError("Completed result exists. Use a new output directory; do not overwrite sealed evaluation.")
    _write_json(output_dir / "frozen_config.json", cfg)
    files = sorted(processed_dir.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files found in {processed_dir}")
    frames, manifest = [], []
    for path in files:
        raw = pd.read_parquet(path)
        frames.append(build_features(raw, cfg))
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        manifest.append({"file": path.name, "bytes": path.stat().st_size, "sha256": digest.hexdigest(), "rows": len(raw)})
        print(f"Features ready: {path.name}, {len(raw):,} raw seconds", flush=True)
    frame = pd.concat(frames, ignore_index=True)
    del frames
    if frame.duplicated(["symbol", "second"]).any():
        raise ValueError("Duplicate symbol/second keys across input files")
    frame["split"] = assign_split(frame["date"], cfg)
    target = f"target_{cfg['primary_horizon_seconds']}s_bps"
    eligible = frame["warmup_complete"] & frame["quote_valid"] & frame[target].notna()
    training = eligible & (frame["split"] == "train") & (frame["second"] % cfg["train_stride_seconds"] == 0)
    validation = eligible & (frame["split"] == "validation")
    testing = eligible & (frame["split"] == "test")
    for name, mask in [("train", training), ("validation", validation), ("test", testing)]:
        if mask.sum() < 10:
            raise ValueError(f"Insufficient {name} rows after quality and warmup filters")
    train = frame.loc[training]
    validation_frame = frame.loc[validation]
    test_frame = frame.loc[testing]
    y_train = train[target].to_numpy()
    eval_cols = ["symbol", "date", "second", "split", "mid"] + [f"target_{h}s_bps" for h in cfg["target_horizons_seconds"]]
    evaluation = frame.loc[validation | testing, eval_cols].copy()
    models, metric_rows = {}, []
    coefficients, preprocessing = [], []
    for model_name, features in MODEL_FEATURES.items():
        print(f"Fitting fixed model: {model_name}; training n={len(train):,}", flush=True)
        if model_name == "zero":
            prediction = np.zeros(len(evaluation))
        else:
            model = _pipeline(model_name, cfg)
            model.fit(train[features], y_train)
            # Bounded prediction batches avoid additional full-size float copies.
            prediction = np.concatenate([model.predict(frame.loc[chunk, features]) for chunk in
                                         np.array_split(evaluation.index.to_numpy(), max(1, int(np.ceil(len(evaluation) / 100000))))])
            models[model_name] = model
            for feature, median in zip(features, model.named_steps["imputer"].statistics_):
                preprocessing.append({"model": model_name, "feature": feature, "training_median": median})
            if model_name.startswith("ridge"):
                for feature, coefficient, mean, scale in zip(features, model.named_steps["model"].coef_, model.named_steps["scaler"].mean_, model.named_steps["scaler"].scale_):
                    coefficients.append({"model": model_name, "feature": feature, "standardized_coefficient": coefficient,
                                         "training_mean_after_imputation": mean, "training_std_after_imputation": scale})
        evaluation[f"prediction_{model_name}"] = prediction
        # Validation is scored before the sealed test metrics are calculated.
        val = evaluation["split"] == "validation"
        metric_rows.append({"split": "validation", "model": model_name,
                            **regression_metrics(evaluation.loc[val, target], prediction[val])})
    best = min(metric_rows, key=lambda row: row["mse"])["model"]
    prediction_col = f"prediction_{best}"
    val_pred = evaluation.loc[evaluation["split"] == "validation", prediction_col]
    threshold = float(val_pred.abs().quantile(cfg["signal_threshold_quantile"]))
    selection = {"selected_model": best, "criterion": "lowest validation MSE; ties use predeclared model order",
                 "absolute_signal_threshold_bps": threshold, "threshold_quantile": cfg["signal_threshold_quantile"],
                 "test_not_used_for_selection": True, "refit_on_validation": False}
    _write_json(output_dir / "selection_before_test.json", selection)
    print(f"Model frozen before test scoring: {best}; signal threshold={threshold:.8f} bps", flush=True)
    test_eval = evaluation.loc[evaluation["split"] == "test"].copy()
    for model_name in MODEL_FEATURES:
        metric_rows.append({"split": "test", "model": model_name,
                            **regression_metrics(test_eval[target], test_eval[f"prediction_{model_name}"])})
    pd.DataFrame(metric_rows).to_csv(output_dir / "model_metrics.csv", index=False)
    evaluation.to_csv(output_dir / "predictions.csv.gz", index=False, compression="gzip")
    pd.DataFrame(coefficients).to_csv(output_dir / "ridge_coefficients.csv", index=False)
    pd.DataFrame(preprocessing).to_csv(output_dir / "preprocessing.csv", index=False)
    import joblib
    joblib.dump({"models": models, "selection": selection, "features": MODEL_FEATURES}, output_dir / "fitted_models.joblib")

    group_metrics = []
    for (split, day, symbol), group in evaluation.groupby(["split", "date", "symbol"]):
        for model_name in MODEL_FEATURES:
            group_metrics.append({"split": split, "date": day, "symbol": symbol, "model": model_name,
                                  **regression_metrics(group[target], group[f"prediction_{model_name}"])})
    pd.DataFrame(group_metrics).to_csv(output_dir / "daily_symbol_metrics.csv", index=False)

    test_eval["squared_error_improvement"] = ((test_eval["prediction_ridge_control"] - test_eval[target]) ** 2 -
                                            (test_eval[prediction_col] - test_eval[target]) ** 2)
    daily = test_eval.groupby("date")["squared_error_improvement"].mean()
    rng = np.random.default_rng(cfg["seed"])
    draws = rng.choice(daily.to_numpy(), size=(cfg["bootstrap_repetitions"], len(daily)), replace=True).mean(axis=1)
    bootstrap = {"estimand": "equal-day mean of control MSE minus selected-model MSE; positive favors selected",
                 "mean_improvement_bps_squared": float(daily.mean()),
                 "percentile_95_ci_bps_squared": np.quantile(draws, [0.025, 0.975]).tolist(),
                 "independent_clusters": int(len(daily)), "cluster": "UTC day, both symbols together",
                 "daily_improvements": daily.to_dict(), "repetitions": cfg["bootstrap_repetitions"],
                 "warning": "Only four test-day clusters in the default protocol; the interval is descriptive and not reliable evidence of statistical significance."}
    _write_json(output_dir / "day_cluster_bootstrap.json", bootstrap)

    horizons = []
    for h in cfg["target_horizons_seconds"]:
        for symbol, group in [("ALL", test_eval)] + list(test_eval.groupby("symbol")):
            horizons.append({"symbol": symbol, "horizon_seconds": h, "model": best,
                             "prediction_type": "frozen 1-second forecast, no horizon-specific refit",
                             **regression_metrics(group[f"target_{h}s_bps"], group[prediction_col])})
    pd.DataFrame(horizons).to_csv(output_dir / "horizon_metrics.csv", index=False)

    quantiles = np.unique(np.quantile(val_pred, np.linspace(0, 1, 11)))
    edges = np.concatenate(([-np.inf], quantiles[1:-1], [np.inf]))
    test_eval["prediction_bin"] = pd.cut(test_eval[prediction_col], edges, labels=False, include_lowest=True)
    calibration = test_eval.groupby("prediction_bin").agg(n=(target, "size"),
                                                         predicted_bps=(prediction_col, "mean"),
                                                         realized_1s_bps=(target, "mean")).reset_index()
    calibration.to_csv(output_dir / "calibration.csv", index=False)

    regime_rows, regime_edges = [], {}
    for column in ("spread_bps", "log_depth", "volatility_30s_bps"):
        cutoff = float(train[column].median())
        regime_edges[column] = cutoff
        values = test_frame.loc[test_eval.index, column]
        for label, mask in [("low", values <= cutoff), ("high", values > cutoff)]:
            subset = test_eval.loc[mask]
            regime_rows.append({"regime_variable": column, "regime": label, "train_median_threshold": cutoff,
                                "model": best, **regression_metrics(subset[target], subset[prediction_col])})
    pd.DataFrame(regime_rows).to_csv(output_dir / "regime_metrics.csv", index=False)

    decisions = test_eval[["symbol", "date", "second", "mid", prediction_col]].rename(columns={prediction_col: "prediction"})
    costs = economic_exercise(frame, decisions, threshold, cfg)
    if not costs.empty:
        costs.to_csv(output_dir / "hypothetical_trades.csv.gz", index=False, compression="gzip")
        aggregates = []
        for group_keys, group in costs.groupby(["entry_delay_seconds", "fee_bps_per_side"]):
            aggregates.append({"symbol": "ALL", "entry_delay_seconds": group_keys[0], "fee_bps_per_side": group_keys[1],
                               "n": len(group), "mean_gross_bps": group["gross_return_bps"].mean(),
                               "mean_net_bps": group["net_return_bps"].mean(), "median_net_bps": group["net_return_bps"].median(),
                               "positive_fraction": (group["net_return_bps"] > 0).mean()})
        for (symbol, delay, fee), group in costs.groupby(["symbol", "entry_delay_seconds", "fee_bps_per_side"]):
            aggregates.append({"symbol": symbol, "entry_delay_seconds": delay, "fee_bps_per_side": fee,
                               "n": len(group), "mean_gross_bps": group["gross_return_bps"].mean(),
                               "mean_net_bps": group["net_return_bps"].mean(), "median_net_bps": group["net_return_bps"].median(),
                               "positive_fraction": (group["net_return_bps"] > 0).mean()})
        cost_summary = pd.DataFrame(aggregates)
    else:
        cost_summary = pd.DataFrame(columns=["symbol", "entry_delay_seconds", "fee_bps_per_side", "n", "mean_gross_bps", "mean_net_bps", "median_net_bps", "positive_fraction"])
    cost_summary.to_csv(output_dir / "cost_sensitivity.csv", index=False)

    # This is an endpoint quote proxy conditional on recent observed trade flow.
    # It is not a markout measured at real executions or evidence of maker fills.
    flow_sign = np.sign(test_frame.loc[test_eval.index, "trade_imbalance_5s"])
    proxy_rows = []
    for flow_label, flow_value in [("sell", -1), ("balanced_or_no_trade", 0), ("buy", 1)]:
        mask = flow_sign == flow_value
        current = test_frame.loc[test_eval.index[mask]]
        for h in cfg["target_horizons_seconds"]:
            y_h = current[f"target_{h}s_bps"]
            # Assumed maker sells at ask to buy flow and buys at bid to sell flow.
            maker_markout = current["spread_bps"] / 2 - flow_value * y_h
            proxy_rows.append({"recent_trade_flow": flow_label, "horizon_seconds": h, "n": int(y_h.notna().sum()),
                               "mean_future_mid_change_bps": y_h.mean(),
                               "hypothetical_quote_side_markout_bps": maker_markout.mean() if flow_value else np.nan,
                               "measurement": "hypothetical quote-side endpoint proxy; no actual fill or queue evidence"})
    pd.DataFrame(proxy_rows).to_csv(output_dir / "markout_proxy.csv", index=False)

    audit = frame.groupby(["split", "date", "symbol"], dropna=False).agg(
        input_seconds=("second", "size"), fresh_quotes=("quote_valid", "sum"),
        warmup_complete=("warmup_complete", "sum"), target_available=(target, "count"),
        min_second=("second", "min"), max_second=("second", "max")).reset_index()
    audit.to_csv(output_dir / "sample_audit.csv", index=False)
    _write_json(output_dir / "input_manifest.json", manifest)
    _write_json(output_dir / "regime_boundaries.json", regime_edges)
    summary = {"selection": selection, "sample_sizes": {"train_sampled": int(training.sum()),
                "validation": int(validation.sum()), "test": int(testing.sum()), "all_input_seconds": len(frame)},
               "features_by_model": MODEL_FEATURES, "metrics": metric_rows, "bootstrap": bootstrap,
               "cost_sensitivity": cost_summary.to_dict("records"), "config": cfg,
               "data_scope": {"symbols": sorted(frame["symbol"].unique()), "dates": sorted(frame["date"].unique())},
               "limitations": ["Two cryptocurrency perpetual futures; no claim of US-equity market validity.",
                   "Fourteen calendar days with only four test-day clusters; event and market-regime concentration.",
                   "One-second snapshots, event-time availability proxy, and assumed trade delay cannot replicate exchange-to-trader latency.",
                   "Quote-crossing returns omit market impact, queue dynamics, funding, and operational frictions; they are hypothetical fixed-notional scenarios.",
                   "Fee scenarios are sensitivity parameters, not a claim about applicable exchange fee schedules.",
                   "Quote-side markouts are conditional proxies, not execution-level realized maker returns.",
                   "All final model comparisons except the validation-selected model are descriptive diagnostics."]}
    _write_json(output_dir / "summary.json", summary)
    print(f"Research complete: {output_dir}", flush=True)
    return _safe_json(summary)
