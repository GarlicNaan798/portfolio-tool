#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

INTERVAL_MINUTES="${PORTFOLIO_INTERVAL_MINUTES:-60}"

PYTHONPATH=src python3 -u -m portfolio_model.runner \
  --universe data/sample_universe.csv \
  --loop \
  --interval-minutes "$INTERVAL_MINUTES"
