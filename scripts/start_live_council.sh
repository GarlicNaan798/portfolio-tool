#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

mkdir -p state

PID_FILE="state/industry_council_live.pid"
LOG_FILE="state/industry_council_live.log"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "Industry council already running with PID $old_pid"
    echo "Log: $LOG_FILE"
    exit 0
  fi
fi

PORTFOLIO_DRY_RUN=false \
PORTFOLIO_EXECUTION_MIN_SCORE=7.5 \
PORTFOLIO_MAX_APPROVED_TRADES=5 \
PORTFOLIO_MIN_TRADES_PER_AGENT=0 \
PORTFOLIO_EXPLORATION_MAX_NOTIONAL=0 \
PORTFOLIO_FORCED_EXPLORATION_MAX_NOTIONAL=0 \
PORTFOLIO_EXPLORATION_BUDGET_FRACTION=0 \
PORTFOLIO_STOP_LOSS_PCT=0.10 \
PORTFOLIO_TAKE_PROFIT_PCT=0.50 \
PORTFOLIO_BUYING_POWER_FRACTION=0.25 \
PORTFOLIO_MAX_TRADE_FRACTION_OF_BUYING_POWER=0.01 \
PORTFOLIO_MAX_POSITION_FRACTION_OF_EQUITY=0.03 \
PORTFOLIO_MIN_CONVICTION_NOTIONAL=1000 \
PYTHONPATH=src \
nohup python3 -u -m portfolio_model.industry_council \
  --universe data/sample_universe.csv \
  --agents-file data/industry_agents.csv \
  --decision-book state/decision_book.json \
  --research-ledger state/research_ledger.csv \
  --research-memory state/research_memory.csv \
  --score-ledger state/opportunity_scores.csv \
  --agent-ledger state/agent_scores.csv \
  --execution-plan state/execution_plan.csv \
  --portfolio-snapshot state/alpaca_portfolio.csv \
  --exit-plan state/exit_plan.csv \
  --industry-agent-count 5 \
  --workers-per-industry 8 \
  --discover-per-industry 120 \
  --candidate-count 10 \
  --target-average-score 7.5 \
  --research-interval-minutes 3 \
  --clock-interval-seconds 10 \
  --execute \
  >> "$LOG_FILE" 2>&1 &

pid="$!"
echo "$pid" > "$PID_FILE"
echo "Started industry council with PID $pid"
echo "Log: $LOG_FILE"
