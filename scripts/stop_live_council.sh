#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PID_FILE="state/industry_council_live.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "No PID file found. The live council is not registered as running."
  exit 0
fi

pid="$(cat "$PID_FILE" || true)"
if [[ -z "$pid" ]]; then
  rm -f "$PID_FILE"
  echo "PID file was empty; cleaned it up."
  exit 0
fi

if kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
  echo "Stopped industry council PID $pid"
else
  echo "PID $pid is not running."
fi

rm -f "$PID_FILE"
