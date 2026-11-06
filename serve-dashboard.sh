#!/usr/bin/env bash
# Start the local read-only dashboard.
#   ./serve-dashboard.sh              # http://localhost:8000, auto-reload
#   ./serve-dashboard.sh --lan        # bind 0.0.0.0 so your phone on the same Wi-Fi can reach it
#   PORT=8123 ./serve-dashboard.sh
set -euo pipefail
cd "$(dirname "$0")"
HOST=127.0.0.1
[[ "${1:-}" == "--lan" ]] && HOST=0.0.0.0
PY=python3
[[ -x .venv/bin/python ]] && PY=.venv/bin/python
echo "Dashboard: http://localhost:${PORT:-8000}  (Ctrl+C to stop)"
exec "$PY" -m uvicorn dashboard.app:app --reload --host "$HOST" --port "${PORT:-8000}"
