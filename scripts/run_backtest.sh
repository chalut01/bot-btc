#!/usr/bin/env bash
# Run backtest with python3 (WSL / Linux / macOS)
PY=python3
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "python3 not found. Please install Python 3.8+ and ensure 'python3' is on PATH."
  exit 1
fi

STRATEGY=${1:-trend}
LIMIT=${2:-200}

exec "$PY" -m btc_bot.backtest --strategy "$STRATEGY" --limit "$LIMIT"
