#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHONPATH=src python3 -u -m portfolio_model.industry_council \
  --universe data/sample_universe.csv \
  --agents-file data/industry_agents.csv \
  --decision-book state/decision_book.json \
  --research-ledger state/research_ledger.csv \
  --research-memory state/research_memory.csv \
  --score-ledger state/opportunity_scores.csv \
  --agent-ledger state/agent_scores.csv \
  --execution-plan state/execution_plan.csv \
  --portfolio-snapshot state/alpaca_portfolio.csv \
  --exit-plan state/exit_plan.csv
