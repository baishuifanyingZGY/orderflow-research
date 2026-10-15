# Research protocol: liquidity-conditioned order flow

Protocol date: 2026-10-14 (America/Detroit). Research observations are historical; their dates and all market timestamps use UTC.

This document specifies the research before inspecting final-test results. It contains no empirical findings. The executed configuration, source manifest, software version, and generated results must accompany the report. Any difference between this protocol and the executed configuration must appear in a change log with its reason and whether test results had already been viewed.

## Question and scope

**Does observed best-quote order-flow imbalance predict subsequent midpoint changes, and does liquidity state help explain when the signal works or fails?** A second analysis asks how the same states relate to hypothetical quote-side forward markouts.

The initial dataset consists of Binance USD-M perpetual futures, `BTCUSDT` and `ETHUSDT`, from 2024-01-01 through 2024-01-14. It is a historical digital-asset microstructure study using top-of-book quotes and aggregate trades. It is not a US equity study, a full-depth order-book reconstruction, an exchange matching-engine simulation, or evidence about any firm's private trading strategies.

The method is motivated by the distinction between contemporaneous price impact and future prediction. Cont, Kukanov and Stoikov relate short-interval price changes to order-flow imbalance and depth. Gould and Bonart study whether queue imbalance predicts the direction of the next midpoint change. Their instruments, targets and data differ from this project; those papers motivate hypotheses rather than supply results for this sample.

- [Cont, Kukanov and Stoikov, The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402)
- [Gould and Bonart, Queue Imbalance as a One-Tick-Ahead Price Predictor in a Limit Order Book](https://arxiv.org/abs/1512.03492)

## Hypotheses fixed before test evaluation

1. Order-flow and queue-imbalance features lower future-return prediction error relative to price and liquidity controls.
2. Adding depth and interactions with spread and recent volatility improves on an unconditional order-flow model.
3. An apparent forecast advantage may weaken with delayed decisions and may not exceed spread, fees and assumed slippage.

Failure to improve a baseline, instability across the four test days, and negative cost-adjusted scenarios are valid outcomes. No positive result is required for project completion.

## Data provenance, rights and budget

Use only the official daily archive under `https://data.binance.vision/data/futures/um/daily/`, with `bookTicker` and `aggTrades` for both symbols. The planned manifest contains 56 ZIP archives: 14 days × 2 symbols × 2 streams. Check file existence, schema and integrity rather than inferring successful acquisition from this count.

The [official archive documentation](https://github.com/binance/binance-public-data) explains daily files and companion SHA-256 checksums. Save each URL, checksum, download date, byte count, row count, schema and processing status in a manifest. Input files are never silently replaced after a run.

The [Binance Vision terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md), version 1.0 dated 2026-08-26 and checked 2026-10-14, allow specified noncommercial research and impose CC BY-NC-SA 4.0 on datasets and derived work, including analytical outputs. Attribute Binance Vision and license published derived reports, charts and data accordingly. Independently authored software uses its separately identified MIT license. No sponsorship is implied.

Data expenditure for this version is **$0**; the user's total data budget ceiling is **$100**. No subscription, paid license, trading account or live trading is part of this protocol.

## Clock, availability and calendar conventions

The default is full UTC days, not US market hours. Build a 1-second grid. For model fitting, use training anchors with `UTC second % 5 == 0`; validation and test retain every eligible second. This deterministic training subsample controls runtime while preserving the one-second target. If storage or runtime requires a fixed daily window, freeze the same window for every symbol and day before any outcome-based selection, record it in configuration, and name it in every report. A window change after viewing performance creates an exploratory variant.

Quotes use `event_time` as a publication-time proxy. A quote is eligible at decision time `t` only if its event time is no later than `t`. Quote transaction time, if present, is metadata and does not replace this availability rule. The archive does not contain the research system's actual receive time.

Aggregate trades use `transact_time + 1,000 milliseconds` as their assumed availability time, because the archive does not provide a corresponding publication timestamp. This one-second delay is a deliberately conservative assumption, not a measured latency or proof that every trade would have arrived. The limitation must appear next to conclusions involving trade features. A quote-only ablation isolates dependence on this assumption.

The clean anchor convention is an integer-second decision time `t`, with quotes selected backward as of `t` and flow measured in `(t-w, t]`. If a storage table uses the start of a one-second bucket, its usable decision time is that bucket's end; do not interpret its opening timestamp as the signal's availability. Preserve deterministic order within equal timestamps. Never interpolate quotes using future observations.

## Audit and exclusions

Before fitting, check and report:

- Positive finite prices, nonnegative quantities, positive usable best-side depth, and bid strictly below ask.
- Timestamp units, event-time ordering, same-time ties, repeated update identifiers, and any order repairs.
- Archive coverage, missing seconds, quote age and stream gaps separately by symbol and day.
- Trades with invalid price, quantity, side or timestamp; duplicate trade identifiers; transactions crossing the assumed availability-day boundary.
- Exact raw-to-processed row counts and every exclusion rule.

The maximum allowed age of each current or future endpoint quote is 1,000 milliseconds. Use the last eligible quote as of an anchor only within that limit; do not fill unavailable grid rows with arbitrarily stale quotes. A retained quote is a historical last observed quote, not a promise of executable liquidity. Rolling features reset at the beginning of each UTC day. Stale quote endpoints are masked; incomplete trailing features are median-imputed using training data only. Exclude the first 60 seconds of each daily session, invalid current/target endpoints, and labels crossing a day boundary. Treat all-day deletion as a manifest exception; do not substitute a better-performing day.

## Signal definitions

Let the observed best bid and ask at event `n` be `b_n` and `a_n`, with base-asset quantities `q_n^b` and `q_n^a`. Let `m_t = (a_t + b_t)/2` and `D_t = q_t^b + q_t^a`.

Queue imbalance:

```text
QI_t = (q_t^b - q_t^a) / D_t
```

Observed best-quote order-flow imbalance contribution:

```text
e_n = I(b_n >= b_prev) * q_n^b
    - I(b_n <= b_prev) * q_prev^b
    - I(a_n <= a_prev) * q_n^a
    + I(a_n >= a_prev) * q_prev^a
OFI_w(t) = sum(e_n for available quote events in (t-w, t])
```

Compute event contributions before downsampling. A calculation using only consecutive one-second endpoint quotes is a different approximation and must be named as such. This measure reflects observed changes to the top quote. It cannot identify every order submission, cancellation, execution or hidden-liquidity event.

For aggregate trade `i`, aggressor sign is `s_i = +1` when `is_buyer_maker` is false and `-1` when it is true. Define trade imbalance over an availability-time window as `sum(s_i * quantity_i) / sum(quantity_i)`, taking zero when the denominator is zero. The archive's maker flag identifies the passive side; it must not be used with the opposite sign. The [official aggregate-trade schema](https://github.com/binance/binance-public-data#aggtrades-1) describes these fields. Aggregates are not individual order-level fills.

The initial feature specification is deliberately small and interpretable:

| Group | Definition | Causal window |
| --- | --- | --- |
| Queue | `QI_t` | Current eligible quote |
| Flow | `OFI_1 / D_t`; `OFI_5 / mean(D, trailing 5 seconds)` | Trailing 1 and 5 seconds |
| Trades | `sum(signed_quantity, 5s) / sum(quantity, 5s)`, zero if no quantity | Trailing available trades; one-second publication assumption applied first |
| Spread | `10000 * (a_t-b_t) / m_t` | Current eligible quote |
| Depth | `log1p(D_t)` using base-asset quantities | Current eligible quote |
| Returns | `10000 * (m_t / m_(t-w) - 1)` | Past 1 and 5 seconds |
| Volatility | Rolling standard deviation of past one-second returns | Trailing 30 seconds |
| Activity | `log1p(sum(quote_updates, 5s))`; `log1p(sum(trade_count, 5s))` | Trailing 5 seconds, after each stream's availability adjustment |
| Interactions | Normalized OFI5 × spread; QI × spread; normalized OFI5 × volatility; QI × volatility | Same causal features |

The control group contains past returns, spread and volatility. The flow group adds QI, OFI, trade imbalance and activity. The liquidity-conditioned group further adds log depth and the four listed interactions. Regime boundaries are the training medians of spread, depth and volatility. No additional feature can be accepted because it improves the held-out test. Cross-symbol features are excluded from the first version. Exact code names, numerical conventions and any pre-test amendment accompany the frozen configuration.

## Prediction targets and splits

Primary target is the future midpoint simple return in basis points:

```text
y_h(t) = 10000 * (m_(t+h) / m_t - 1)
primary h = 1 second
diagnostic h = 5 and 10 seconds
```

Both endpoint midpoints use backward as-of eligible quotes, subject to the same quality rules. A zero-return prediction is an explicit benchmark. Horizon comparisons are exploratory diagnostics; the best horizon is not retroactively declared primary.

| Partition | Inclusive UTC dates | Purpose |
| --- | --- | --- |
| Training | 2024-01-01 to 2024-01-07 | Feature statistics, model fitting and training-only state thresholds |
| Validation | 2024-01-08 to 2024-01-10 | Select among the prespecified model and hyperparameter candidates |
| Locked test | 2024-01-11 to 2024-01-14 | One final evaluation of frozen choices |

All symbols share the same boundaries. A training label may not reach validation, and a validation label may not reach test. Require each label and every execution-scenario exit to lie within its permitted segment. Do not use random shuffled train/test splits. Report the actual retained sample sizes and purged rows.

Fit median imputers, standardization and model parameters on training data only. Retain the training-fit models after validation selection; this first run does not refit on validation. Choose the hypothetical trading threshold on validation data. Use seed `1729` and record package versions, candidate specifications and selection metric. A digest of the run configuration and model metadata supports an audit trail; it is not independent proof of preregistration.

## Models and statistical reporting

The fixed comparison contains zero prediction, Ridge regression on the control group, a quote-only Ridge ablation excluding the two trade features, Ridge on the full flow group, Ridge on the liquidity-conditioned group, and one histogram gradient boosting model. All Ridge models use `alpha=100`. The tree model uses `max_iter=100`, `max_depth=3`, `max_leaf_nodes=15`, `l2_regularization=10`, `learning_rate=0.05`, and `early_stopping=False`. Median imputation and standardization are fitted on training only. Select the primary forecasting model by the lowest validation one-second MSE; report all candidates' test outcomes so selection does not hide weaker models. Any optional model not executed must be identified as planned, not completed.

Primary score is MSE for the one-second target. Report `1 - MSE_model / MSE_zero` as **R² relative to zero prediction**, to distinguish it from implementations that center around the test mean. Pair this with the MSE difference between nested feature groups. Include per-symbol and per-day scores, signal-return correlation, prediction calibration or bins, and sample counts. Direction accuracy on nonzero returns must include the fraction of observations retained by that filter.

Dependence matters: neighboring labels overlap for the longer horizons, and BTC and ETH share market shocks. The initial uncertainty diagnostic uses 5,000 resamples of the four complete UTC test-day blocks, keeping both symbols together. The statistic is the average daily mean of `control squared error - selected-model squared error`; positive values favor the selected model. This is a descriptive bootstrap based on only four independent time clusters, not strong statistical confirmation. Show every test-day outcome even when the pooled score is favorable, and identify model-selection uncertainty as unmodeled. Four test days provide weak evidence about long-run stability. Do not report an annualized Sharpe or a precise claim of persistent alpha from this study.

## Economic interpretation and quote-side markouts

Separate predictive accuracy from hypothetical economic value. A quote-side markout at decision time `t` is:

```text
bid-side markout_h = 10000 * (m_(t+h) - b_t) / m_t
ask-side markout_h = 10000 * (a_t - m_(t+h)) / m_t
```

These ask what the subsequent midpoint would imply if a unit had executed at the displayed side at `t`. They are **hypothetical quote-side markouts**, not actual trade-conditioned maker outcomes or realized profits. The first implementation reports an ask-side proxy following positive recent trade flow and a bid-side proxy following negative recent trade flow, with counts and horizons; it does not estimate actual trade-conditioned markouts. There is no order queue, fill probability, partial-fill model or measured cancellation delay in these data products.

If a trade-conditioned event study is added, its explanatory state must strictly precede the execution. A one-second bar that includes an execution is not a valid pre-execution state. Aggregated trade time, publication-time ambiguity and incomplete event ordering must be resolved explicitly before labeling such an extension as actual execution markouts.

For active-trade scenarios, use only anchors with `UTC second % 10 == 0`. Trade in the sign of the selected model's forecast only when its absolute value meets the 90th percentile of absolute validation forecasts. Keep this threshold fixed in test. Test entry delays of 0, 1 and 2 seconds followed by a 5-second holding interval. A buy enters at the later observed ask and exits at bid; a sell enters at bid and exits at ask. This is a negligible-size, fixed-notional hypothetical round trip. Fee scenarios are 0, 1 and 5 basis points **per side**; each complete trade pays both sides. If extra slippage is not modeled, say so. A one-second forecast is being used to gate this separate five-second economic diagnostic; do not describe it as the identical statistical target.

Delay experiments must match timestamp resolution. With one-second processed quotes, use integer-second delays or retain raw quotes for subsecond scenarios; do not manufacture 10-millisecond latency conclusions by interpolating one-second bars. Report gross advantage, spread, assumed fees, extra slippage, coverage and net outcome separately. A zero-cost column is a diagnostic, not the realistic trading case.

The archives do not establish executable quantities at signal-arrival time. Market impact, queue position, account fee tier, receive-time latency, inventory financing, funding settlements and margin constraints are not fully modeled. Fees are explicitly hypothetical sensitivity parameters, not assertions of the actual 2024 account schedule. Avoid holding periods that cross funding events if no funding data are joined; otherwise label funding omission. Repeated overlapping hypothetical trades cannot be added into an investable equity curve without explicit position accounting.

## Meaningful correctness checks

- Verify the OFI formula on unchanged, improved and worsened bid/ask prices with hand-calculated expectations.
- Prefix invariance: computing features on a data prefix yields the same prefix features as computing on the complete input.
- Future perturbation: changing records after a decision cannot alter that decision's features.
- Apply the trade-availability delay before aggregation; test trades immediately around a second and day boundary.
- Ensure backward as-of quote matches never use an event after the decision time.
- Check zero-volume windows, duplicate timestamps, first-event handling, gaps, and warm-up resets.
- Assert labels and scenario exits do not cross split/day boundaries.
- Perturb test values and verify training preprocessing and parameters remain unchanged.
- Use synthetic price paths to check long/short markout signs and that both spread crossings and both fees are charged.
- Compare chunked processing with a small in-memory reference so chunk boundaries do not lose quote transitions or trades.

These tests validate research plumbing. Synthetic fixtures are never presented as empirical market evidence.

## Deliverables and permitted conclusions

The deliverable is code, reproducible configuration, source manifest, data audit, experiment log, checks, visual results, an English research report and a presentation narrative. Useful visuals include daily coverage, feature calibration, incremental model scores, horizon decay, cost/latency sensitivity and quote-side markouts by liquidity state.

Every headline names the instrument, dates and sample limitation. Positive claims require generated results; empty or failed runs remain visible. A justified conclusion may be that a weak statistical relationship does not survive cost assumptions. Public descriptions should identify the work as an AI-assisted independent research project and attribute actual contributions accurately. The report makes no claim of employment, collaboration, approval or endorsement by Citadel Securities, MIT or Binance.

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
