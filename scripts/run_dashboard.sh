#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHONPATH=src python3 -u -m portfolio_model.dashboard --host 127.0.0.1 --port 8765 --state-dir state
