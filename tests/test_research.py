"""Tests target temporal leakage, partition integrity, and execution accounting."""
import numpy as np
import pandas as pd
import pytest

from orderflow.research import (
    LIQUIDITY_FEATURES, assign_split, build_features, economic_exercise,
    regression_metrics, resolved_config,
)


def observations(start="2024-01-01T00:00:00Z", n=180, symbol="BTCUSDT"):
    second = int(pd.Timestamp(start).timestamp()) + np.arange(n)
    mid = 100 + np.arange(n) * .001
    return pd.DataFrame({"second": second, "symbol": symbol,
                         "bid": mid - .01, "ask": mid + .01,
                         "bid_qty": 2 + np.arange(n) % 3, "ask_qty": 3,
                         "ofi": np.sin(np.arange(n)), "quote_updates": 5,
                         "trade_qty": 2.0, "signed_trade_qty": 0.5,
                         "trade_count": 2, "quote_age_ms": 10})


def test_future_perturbation_cannot_change_features():
    raw = observations()
    original = build_features(raw)
    altered = raw.copy()
    numeric = ["bid", "ask", "bid_qty", "ask_qty", "ofi", "quote_updates",
               "trade_qty", "signed_trade_qty", "trade_count"]
    altered.loc[101:, numeric] *= 10
    changed = build_features(altered)
    pd.testing.assert_frame_equal(original.loc[:100, LIQUIDITY_FEATURES], changed.loc[:100, LIQUIDITY_FEATURES])
    assert original.loc[100, "target_1s_bps"] != changed.loc[100, "target_1s_bps"]


def test_targets_and_warmup_do_not_cross_midnight_or_symbol():
    first = observations("2024-01-01T23:58:30Z", 90)
    second = observations("2024-01-02T00:00:00Z", 90)
    second[["bid", "ask"]] *= 2
    other = observations("2024-01-01T23:58:30Z", 90, "ETHUSDT")
    other[["bid", "ask"]] *= 4
    result = build_features(pd.concat([first, second, other], ignore_index=True))
    for _, group in result.groupby(["symbol", "date"]):
        assert group.iloc[-1]["target_1s_bps"] != group.iloc[-1]["target_1s_bps"]
        assert group.iloc[-10:]["target_10s_bps"].isna().all()
        assert not group.iloc[:60]["warmup_complete"].any()
        assert group.iloc[60:]["warmup_complete"].all()
        assert pd.isna(group.iloc[0]["return_1s_bps"])


def test_stale_quotes_and_missing_seconds_are_not_forward_filled():
    raw = observations()
    raw.loc[100, "quote_age_ms"] = 1001
    raw = raw.drop(index=110)
    result = build_features(raw)
    assert not result.loc[100, "quote_valid"]
    assert pd.isna(result.loc[100, "mid"])
    assert pd.isna(result.loc[99, "target_1s_bps"])
    assert not result.loc[110, "quote_valid"]
    assert pd.isna(result.loc[109, "target_1s_bps"])
    assert pd.isna(result.loc[111, "return_1s_bps"])


def test_chronological_split_excludes_unlisted_dates_and_rejects_overlap():
    dates = pd.Series(["2024-01-07", "2024-01-08", "2024-01-10", "2024-01-11", "2024-01-15"])
    assert assign_split(dates).tolist() == ["train", "validation", "validation", "test", "excluded"]
    with pytest.raises(ValueError, match="disjoint"):
        resolved_config({"test_dates": ["2024-01-01"]})
    with pytest.raises(ValueError, match="chronological"):
        resolved_config({"test_dates": ["2023-01-01"]})


@pytest.mark.parametrize("prediction", [1.0, -1.0])
def test_flat_market_crossing_loses_spread_for_both_sides(prediction):
    second = int(pd.Timestamp("2024-01-11T00:00:00Z").timestamp())
    quotes = pd.DataFrame({"symbol": "BTCUSDT", "second": second + np.arange(20),
                           "date": "2024-01-11", "bid": 99.0, "ask": 101.0,
                           "quote_valid": True})
    decision = pd.DataFrame({"symbol": ["BTCUSDT"], "date": ["2024-01-11"],
                             "second": [second], "mid": [100.0], "prediction": [prediction]})
    result = economic_exercise(quotes, decision, .5)
    assert len(result) == 9
    assert np.allclose(result["gross_return_bps"], -200)
    assert np.allclose(result["net_return_bps"], -200 - 2 * result["fee_bps_per_side"])
    assert (result["exit_second"] - result["entry_second"] == 5).all()


def test_delayed_execution_uses_delayed_quotes_and_drops_stale_exit():
    second = int(pd.Timestamp("2024-01-11T00:00:00Z").timestamp())
    quotes = pd.DataFrame({"symbol": "BTCUSDT", "second": second + np.arange(20),
                           "date": "2024-01-11", "bid": 99.0 + np.arange(20),
                           "ask": 101.0 + np.arange(20), "quote_valid": True})
    quotes.loc[7, "quote_valid"] = False
    decision = pd.DataFrame({"symbol": ["BTCUSDT"], "date": ["2024-01-11"],
                             "second": [second], "mid": [100.0], "prediction": [1.0]})
    result = economic_exercise(quotes, decision, .5)
    assert set(result["entry_delay_seconds"]) == {0, 1}
    assert set(result.loc[result["entry_delay_seconds"] == 1, "entry_price"]) == {102.0}
    assert np.allclose(result["gross_return_bps"], 300)


def test_metrics_use_zero_baseline_and_ignore_zero_direction_labels():
    metrics = regression_metrics(np.array([0., 1., -1.]), np.array([0., 0.5, -0.5]))
    assert metrics["r2_vs_zero"] == pytest.approx(.75)
    assert metrics["directional_accuracy"] == 1
    assert metrics["nonzero_target_count"] == 2
