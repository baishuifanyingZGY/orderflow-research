# Presentation guide / 中文导读

## 项目定位

本项目研究真实交易所最优买卖报价中的订单流信息，能否预测下一秒公布的中间价变化，以及价差、手续费和延迟是否会消耗这种优势。

数据：BTCUSDT、ETHUSDT 永续合约，2024 年 1 月 1-14 日。约 5.39 亿条报价更新、4,027 万条聚合成交记录，数据费用 $0。它是短期历史市场微观结构研究，没有美股实证、真实成交或机构内部策略的含义。

核心结果：验证集选出的树模型，测试集相对零预测的 R² 为 4.416%，比价格控制模型降低约 4.437% MSE。假设 1 秒入场延迟、每边 1 bp 手续费，五秒往返平均结果为 -1.941 bp。只有四个测试日，因此不据此声称持久盈利或强统计显著性。

## 90-second English introduction

> My project asks whether observed order flow predicts short-term price changes,
> and whether that information remains useful after trading frictions.
>
> Using an AI-assisted research workflow, the project processes roughly 539
> million best-quote updates and 40 million aggregate trade records for Bitcoin
> and Ether perpetual futures over fourteen days. It compares simple price
> controls, quote and trade-flow factors, liquidity interactions, and a small
> boosted-tree model. The split is chronological: seven days for training,
> three for validation, and four for the final test.
>
> The selected model reduces test mean squared error by about 4.44 percent
> relative to price controls. But a one-second delay and one basis point of
> fees on each side turn the hypothetical round-trip result negative.
>
> The central finding is that predictability and tradability are different
> questions. The study also found interleaved source records and publication
> delays, which made data validation as important as modeling. These are
> historical diagnostics, not live trading results, and the next step is a
> longer independent sample with better timing and execution evidence.

Use this as a description of the completed project. The repository explicitly
records the AI implementation; do not describe coding or experiments as unaided
work you personally performed.

## Five-minute walkthrough

### 0:00-0:45 — Question

Show the first report page. Explain why a liquidity provider cares about the
next price movement: a favorable-looking quote can be followed by an adverse
move. Define the midpoint as `(best_bid + best_ask) / 2`. The project predicts a
future midpoint update, not the return during the feature-construction window.

### 0:45-1:30 — Data and timing

Show the coverage chart. Explain the distinction between exchange transaction
time, exchange publication time and a research system's actual receive time.
The first two exist for books; the third is absent. Trades have transaction
time and use an explicit one-second availability assumption. Describe the
interleaved January 2 source file and why sorting must happen before OFI.

### 1:30-2:15 — Factors and baselines

Queue imbalance compares displayed size on the two best sides. OFI measures
changes in observed supply and demand across successive best quotes. Explain
why OFI is calculated for every update before aggregation, then introduce
recent returns, volatility and spread as controls. The quote-only baseline
tests whether trade timing is essential to the result.

### 2:15-3:00 — Validation and findings

Show the model chart. Emphasize that validation selected the model before test
scoring. Preprocessing was fitted only on training data. Quote-only Ridge has
about 3.41% test R² versus zero; the selected tree reaches 4.42%. The liquidity
interaction model does not improve consistently across validation and test.
Do not use the 70% direction statistic without explaining that it excludes
zero-price-change observations, which make up about half the sample.

### 3:00-4:00 — Economic diagnostic

Show the cost heatmap. All figures already cross the quoted bid/ask spread.
At zero extra fees, average hypothetical return falls from 0.656 bp at zero
delay to 0.059 bp after one second. At one bp per side, the one-second-delay
result is -1.941 bp. This is a fixed-notional complete-case scenario, not a
portfolio backtest: future missing prices are excluded, and impact, funding
and operational constraints are absent.

### 4:00-5:00 — Limits and next experiment

Show the four daily outcomes. Four correlated-calendar-time clusters are too
few to establish generality. Explain retained publication backlogs and why
freshly published quotes need not represent fresh market state. Propose a
new date holdout, explicit transaction-age checks and a separate equity
replication with licensed data. Keep the current results intact.

## Technical questions and short answers

| Question | Answer to understand, not memorize |
| --- | --- |
| Why not randomly split seconds? | Nearby observations share market state; longer labels overlap. Chronological dates better separate training from future evaluation. |
| Why a zero forecast? | Short-horizon returns are noisy and often zero. Complexity must beat a strong trivial reference. |
| Why a control model? | To test whether order flow adds information beyond recent returns, spread and volatility. |
| Is contemporaneous price impact an alpha? | No. Explaining a price movement during the OFI window does not establish prediction of a later movement. |
| Does 4.416% R² mean a 4.416% return? | No. It is the reduction in squared forecast error relative to zero prediction. |
| Why preserve equal-time updates? | Several book transitions can occur within one millisecond. Removing them before OFI can change the factor. |
| What was the source-data bug? | One official daily file interleaved early and late records. A streaming filter would discard valid data; external ordering retained the entire day. |
| What does the maker flag mean? | `is_buyer_maker=true` means the buyer was passive, so the aggressive trade was a sell. |
| Is quote age the same as market-state age? | No. Age since publication can be small while the underlying transaction is old. The report discloses retained backlogs. |
| Does the bootstrap prove significance? | No. It resamples only four UTC days, jointly across both assets. Its interval is descriptive. |
| Are the cost estimates actual fills? | No. They cross historical quotes at specified times and assume negligible size. Future-price availability also conditions the sample. |
| Are markouts measured on actual maker fills? | No. They are explicitly labeled quote-side proxies conditional on recent trade flow. |
| Can these results be called a Citadel strategy? | No. They address publicly relevant market-making research questions without any firm affiliation or internal information. |
| What did AI do? | The objective and budget came from the project owner; AI implemented the study, experiments, checks and documentation. Explain that workflow accurately. |

## 口语练习顺序

1. 用自己的话解释 midpoint、spread、OFI、leakage、out-of-sample。
2. 不看稿说清楚研究问题、数据、切分、结果、限制，各一句。
3. 对着两张核心图讲两分钟，不用背数字到小数点后三位。
4. 回答上面的技术追问，卡住时回到代码或研究协议查证。
5. 能解释为何结果不足以证明盈利，再练完整五分钟版本。
