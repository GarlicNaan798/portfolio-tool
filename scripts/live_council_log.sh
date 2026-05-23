#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

tail -n "${1:-80}" state/industry_council_live.log
