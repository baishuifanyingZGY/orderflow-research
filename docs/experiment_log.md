# Experiment log

## Before model evaluation

- Fixed BTCUSDT and ETHUSDT, Jan 1-14 2024, full UTC days, one-second grid and target.
- Training Jan 1-7, validation Jan 8-10, final test Jan 11-14. Seed 1729.
- Raw archives are verified against vendor SHA-256 checksums.
- Data audit detected interleaved early-day and late-day events in BTCUSDT Jan 2. The initial stream-only filter was rejected before any model evaluation because it dropped most of that day. Original intermediate artifacts are retained locally in tmp/quarantine.
- Fixed the loader to halt on source disorder, externally sort by event_time/update_id, remove only exact duplicate records, and then calculate every observed BBO transition. All dates are retained.
- Added the quote-only Ridge ablation before model evaluation to isolate the assumed trade-availability lag. No selection used test outcomes.
- Prediction and economic scenarios remain separate: one-second forecast; diagnostic five-second quote-crossing round trip.

Results are generated once from this frozen protocol. Report generation does not refit models.

## First completed evaluation and independent review

- All 28 symbol-days retained; all 56 vendor checksums verified. Final features computed from 538,977,734 quote updates and 40,271,937 aggregate trade records.
- Validation selected the prespecified histogram gradient boosting model. Test results were not used to change model settings or features.
- Report generation reads saved outputs only; no refitting or result selection.
- Independent source review found no blocking train/test leakage or spread/fee sign bug. It identified the retained publication-backlog and future-data-availability conditions, now disclosed in the report and README. No test-informed filter was introduced.
- Final code checks cover OFI signs, same-time updates, chunk invariance, source-order repair, future perturbation, daily boundaries, stale observations and both long/short execution costs.
