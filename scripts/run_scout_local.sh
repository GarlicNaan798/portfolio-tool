#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

INTERVAL_MINUTES="${PORTFOLIO_INTERVAL_MINUTES:-60}"
RESEARCH_AGENTS="${PORTFOLIO_RESEARCH_AGENTS:-4}"
DISCOVER_LIMIT="${PORTFOLIO_DISCOVER_LIMIT:-50}"

PYTHONPATH=src python3 -u -m portfolio_model.runner \
  --universe data/sample_universe.csv \
  --auto-research \
  --loop \
  --interval-minutes "$INTERVAL_MINUTES" \
  --research-agents "$RESEARCH_AGENTS" \
  --discover-limit "$DISCOVER_LIMIT"
