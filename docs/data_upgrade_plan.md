# Data upgrade and budget plan

Planning date: 2026-10-14 (America/Detroit). This is a plan, not a purchase record or a claim that an upgrade has been completed.

## Budget and first deliverable

| Item | Initial choice | Data cost |
| --- | --- | ---: |
| Instruments | Binance USD-M `BTCUSDT` and `ETHUSDT` perpetual futures | $0 |
| Dates | 2024-01-01 through 2024-01-14, UTC | $0 |
| Streams | Official daily `bookTicker` and `aggTrades` | $0 |
| Partitions | 7 training days, 3 validation days, 4 locked test days | $0 |
| Planned archives | 56 ZIP files plus checksums | $0 |
| Paid data ordered for this version | None | $0 |
| Remaining user-authorized data ceiling | Available for a justified later upgrade | $100 |

Archive size is an acquisition estimate until recorded in the manifest. Streaming downloads and chunked reductions avoid requiring all uncompressed records in memory. Full UTC-day analysis is the default. Any fixed-hour sampling window must be chosen consistently before inspecting outcomes and disclosed in the results.

The first version can be complete and presentable without spending the budget. Retaining a reproducible negative result is preferable to buying more data only in search of a positive backtest.

## Current rights and publication packaging

The [Binance Vision terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md), checked 2026-10-14, provide noncommercial research access under CC BY-NC-SA 4.0. Derived reports, charts, models and data require corresponding attribution and licensing. Commercial or live-production use needs separate permission under the provider's terms. Preserve the terms version applicable at download.

Keep original software under a separate MIT notice. Label derived artifacts independently; a repository-wide MIT badge cannot relicense provider data. Prefer publishing download instructions, checksums and compact research outputs instead of large raw archives. Name Binance Vision as source without suggesting endorsement. See the [license text](https://creativecommons.org/licenses/by-nc-sa/4.0/) and [official archive instructions](https://github.com/binance/binance-public-data).

The originally considered LOBSTER free-sample route is not used in this project's empirical outputs. Public availability of a sample does not establish permission to publish sample-derived research. Any future LOBSTER work must first verify a valid license and publication rights for the intended artifacts against its current terms. No equity-data entitlement is assumed or included in the budget.

## Upgrade order

### 1. More independent days before more features

Extend the same two instruments to a longer fixed period, then reserve a new block of days that has never participated in feature design or model selection. Use the same download, audit and transformation pipeline. This can still cost $0 where the official archive has the required streams. Confirm exact coverage before promising a month or quarter.

More dates improve the opportunity to observe changing volatility, liquidity and calendar conditions. They do not establish regime coverage by themselves. Name the chosen dates, weekday/weekend mix and event context; do not choose only dates where the initial model looks favorable.

### 2. Better timing and execution evidence

The highest-priority quality upgrade is data with documented exchange publication and receiver timestamps, or a carefully recorded prospective stream with a local receive clock. The present archive uses book `event_time` as a proxy and a one-second assumed trade delay. Additional depth cannot repair a missing availability clock.

Next consider fuller depth or order-level messages when the proposed question actually needs them. Queue-position and fill-probability work requires more than best bid/ask sizes. A provider's claim of L2 or L3 must be matched to its exact message schema, snapshots, sequence handling and session-start reconstruction.

Any prospective collection would need sufficient elapsed observation time and a defined data-integrity process. It is an extension, not a hidden dependency of the current deliverable.

### 3. Transfer to US equities only with a separate study

A later US equity version would use a named venue/feed and documented redistribution rights. Its market hours, tick size, fees, consolidated-price context and event semantics differ from perpetual futures. Preserve the research methodology, then rerun data validation, targets and costs from first principles; do not present the digital-asset findings as equity results.

Potential options are an existing university entitlement or a quote for a narrow paid historical window. Obtain the exact provider quote and terms before promising coverage. No current provider price, free credit or academic entitlement is assumed. Prioritize multiple days for a few instruments over a single day with many instruments.

## Purchase gate within the $100 ceiling

A paid acquisition should be made only when its reviewable specification contains:

1. Dataset, venue, symbols, dates, timestamp fields and depth/message type.
2. What unresolved research question it improves over the $0 version.
3. Exact one-time total including fees/taxes, any recurring obligation, and cumulative data spending no greater than $100.
4. License for intended research, GitHub-derived outputs and portfolio presentation.
5. A small schema/coverage check, download method and storage estimate.

This checklist makes an upgrade concrete; it does not imply that the user must repeat an already sufficient authorization. Where a purchase requires credentials or a human checkout, prepare the exact specification first. Never subscribe silently, assume a free trial remains free, or spend above the ceiling.

## Evidence required to call an upgrade complete

Record the invoice or $0 source, terms version, full file manifest, checksums, download date, quality exclusions and actual dates received. Add the new partition and timing policy to a fresh frozen run configuration. Keep earlier outputs and label the new experiment separately. Report whether conclusions changed, including unfavorable outcomes; do not overwrite the historical test with a more attractive sample.
