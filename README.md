# Portfolio Tool

A medium-horizon equity research model inspired by disciplined quant investing principles:

- no high-frequency or intraday trading assumptions
- fundamentals before price action
- valuation compared with industry peers
- year-over-year growth and balance-sheet quality
- sentiment as a risk-adjusted input, not the whole thesis
- turnover controls, holding-period discipline, and hysteresis

This is not financial advice and does not place trades. It is a research scaffold for ranking equities and producing portfolio actions from explicit inputs.

## Quick Start

```bash
PYTHONPATH=src python3 -m portfolio_model.cli --universe data/sample_universe.csv
```

Run tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
```

## Alpaca Execution

The code reads Alpaca credentials from environment variables. Use paper trading first:

```bash
export APCA_API_KEY_ID="your_paper_key_id"
export APCA_API_SECRET_KEY="your_paper_secret_key"
export ALPACA_BASE_URL="https://paper-api.alpaca.markets"
export PORTFOLIO_DRY_RUN=true
```

Or create a local `.env` file in the project root with the same variables. `.env` is ignored by git.

Never commit real keys. If a key is pasted into chat, logs, screenshots, or source code, revoke it in Alpaca and create a fresh paper key.

Run the model plus execution guard:

```bash
PYTHONPATH=src python3 -m portfolio_model.runner --universe data/sample_universe.csv
```

Run continuously on this device:

```bash
PYTHONPATH=src python3 -m portfolio_model.runner --universe data/sample_universe.csv --loop --interval-minutes 60
```

Stop it any time with `Ctrl+C`. Your computer must stay awake and connected to the internet for scheduled research or Alpaca access to work.

You can also use the local helper script:

```bash
bash scripts/run_local.sh
```

Run the parallel online research scout locally:

```bash
PYTHONPATH=src python3 -u -m portfolio_model.runner --universe data/sample_universe.csv --auto-research --research-agents 4 --discover-limit 50
```

Run the scout continuously:

```bash
PYTHONPATH=src python3 -u -m portfolio_model.runner --universe data/sample_universe.csv --auto-research --loop --interval-minutes 60 --research-agents 4
```

Or use the helper script:

```bash
bash scripts/run_scout_local.sh
```

The scout uses Alpaca for tradable assets, latest bars, and news, SEC company facts for objective fundamentals, and one deterministic sentiment scorer so every worker applies the same sentiment rules.
If Alpaca market data is unavailable, it can fall back to prices in `data/sample_universe.csv` for symbols in the watchlist.

## Pre-Market Decision Framework

Run research continuously before market open, save the latest decision book, and execute that book once Alpaca reports the market is open:

```bash
bash scripts/run_preopen_local.sh
```

By default this researches, saves `state/decision_book.json`, watches Alpaca's `/v2/clock`, and **does not place orders**.
Each cycle also appends to `state/research_ledger.csv` and rewrites `state/research_memory.csv` with only currently desirable equities. Unowned equities below `PORTFOLIO_MEMORY_MIN_SCORE` are marked `DISPOSED` in the ledger and removed from active memory.

Paper execution at open requires both an execution flag and dry-run disabled:

```bash
PORTFOLIO_DRY_RUN=false PYTHONPATH=src python3 -u -m portfolio_model.preopen \
  --universe data/sample_universe.csv \
  --decision-book state/decision_book.json \
  --research-agents 4 \
  --discover-limit 250 \
  --execute
```

To research Alpaca-discovered assets instead of the local watchlist, leave `--watchlist` empty. For a curated universe, pass a watchlist CSV with `symbol,industry`.

## Five-Agent Industry Council

Run five industry-focused agents that keep researching until the top opportunity set reaches the target average score:

```bash
bash scripts/run_industry_council_local.sh
```

The default agents are Software, Energy, Consumer Staples, Healthcare, and Industrials. Each industry agent runs eight parallel research workers by default and audits every researched symbol across price, SEC fundamentals, valuation, growth, quality, news sentiment, DCF, and portfolio-context checks. Each agent scores researched equities on a 0-10 opportunity scale that prioritizes valuation/growth/quality/DCF metrics and treats sentiment as a smaller risk-adjustment input. When the average score of the top `PORTFOLIO_TARGET_CANDIDATE_COUNT` names reaches `PORTFOLIO_TARGET_AVERAGE_SCORE`, research stops for the day and the process waits for Alpaca market open.

Outputs:

```text
state/decision_book.json
state/research_ledger.csv
state/research_memory.csv
state/opportunity_scores.csv
```

Check live progress from disk:

```bash
bash scripts/status.sh
```

To submit paper orders after reviewing output:

```bash
PORTFOLIO_DRY_RUN=false PYTHONPATH=src python3 -m portfolio_model.runner --universe data/sample_universe.csv --execute
```

Continuous paper execution is also supported, but keep `PORTFOLIO_DRY_RUN=true` until you have reviewed order sizing:

```bash
PORTFOLIO_DRY_RUN=false PYTHONPATH=src python3 -m portfolio_model.runner --universe data/sample_universe.csv --loop --interval-minutes 60 --execute
```

Live trading should only be enabled after paper trading, reconciliation, order-size review, and explicit risk limits.

## Input Format

The model expects CSV columns like:

```csv
symbol,industry,price,pe,pb,fcf_yield,revenue_yoy,eps_yoy,gross_margin,debt_to_equity,sentiment,sentiment_confidence,current_weight,holding_days
```

Sentiment should be normalized from `-1.0` to `1.0`, where negative values are bearish and positive values are constructive. `sentiment_confidence` should be `0.0` to `1.0`.

## Philosophy

The model is built around cross-sectional ranking rather than short-term prediction. It rewards companies that look statistically inexpensive versus their industry, have evidence of real operating growth, carry manageable leverage, and have sentiment that supports rather than overwhelms the fundamental case.

Trading decisions include minimum holding days and score hysteresis so the model does not churn positions on tiny signal changes.
