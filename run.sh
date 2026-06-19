#!/usr/bin/env bash
# Start the Deck Replicator web app.
set -euo pipefail

if [ -f .env ]; then
  set -a; . ./.env; set +a
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "warning: ANTHROPIC_API_KEY is not set — content generation will fail until it is." >&2
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "Deck Replicator → http://${HOST}:${PORT}"
exec uvicorn app.main:app --host "$HOST" --port "$PORT" "$@"
