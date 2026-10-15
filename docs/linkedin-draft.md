# LinkedIn project draft

This text describes completed work. It has **not** been posted to LinkedIn.
The GitHub repository was private when publishing this version; external
viewers need access unless the owner later changes visibility.

## Project title

**Order-Flow Predictability and Trading Frictions — AI-Assisted Quant Research**

## Project description

An independent, reproducible study of short-horizon market microstructure using
BTC and ETH perpetual-futures data. The pipeline processes 538.98 million
observed best-quote updates and 40.27 million aggregate trade records from
fourteen historical days, with checksummed source files and documented data
repairs.

The research compares causal order-flow factors, quote-only ablations,
liquidity interactions and simple machine-learning models under a chronological
train/validation/test split. The validation-selected model reduces held-out
MSE by 4.44% relative to price controls. However, the hypothetical execution
advantage disappears under the tested fee and delay assumptions.

The repository includes code, correctness tests, the research protocol, data
audit, complete result tables and an eight-page report. AI was used for research
implementation and documentation. Results are historical, limited to four test
days, and do not establish live trading profitability.

Repository: https://github.com/baishuifanyingZGY/orderflow-research

## Optional post

I completed an AI-assisted research project on a question at the intersection
of market microstructure and machine learning: when does order flow predict
prices, and when does that information survive trading frictions?

The study uses real BTC/ETH quote and trade archives, chronological validation,
and explicit cost scenarios. The selected model improves held-out forecast
error, but one second of delay and one basis point of fees per side erase the
hypothetical economic advantage.

The most useful findings came from separating data quality, prediction and
execution. An interleaved daily archive required chronological reconstruction;
publication backlogs required careful interpretation of what a forecast means.

Code, methodology and findings are documented in the project. This is a short
historical research sample, with the next step being a longer independent
validation window and stronger timing evidence.

#QuantitativeResearch #MarketMicrostructure #Python #MachineLearning

## Claim boundaries

Use "independent project" and "AI-assisted." Do not imply employment at,
collaboration with, sponsorship by or approval from Citadel Securities, MIT or
Binance. Do not call hypothetical quote scenarios realized returns, or claim
that a private repository is accessible to everyone.
