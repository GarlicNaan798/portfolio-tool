#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

RESEARCH_AGENTS="${PORTFOLIO_RESEARCH_AGENTS:-4}"
DISCOVER_LIMIT="${PORTFOLIO_DISCOVER_LIMIT:-250}"

PYTHONPATH=src python3 -u -m portfolio_model.preopen \
  --universe data/sample_universe.csv \
  --decision-book state/decision_book.json \
  --research-ledger state/research_ledger.csv \
  --research-memory state/research_memory.csv \
  --research-agents "$RESEARCH_AGENTS" \
  --discover-limit "$DISCOVER_LIMIT"
