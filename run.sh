#!/usr/bin/env bash
# Start the FairLens sandbox and dashboard. Demo preset is Model 2 -> 7 -> 5.
set -euo pipefail
cd "$(dirname "$0")"
PY=./.venv/Scripts/python.exe
if [ ! -f "$PY" ]; then PY=./.venv/bin/python; fi
if [ -f .env ]; then set -a; . ./.env; set +a; fi

$PY -m uvicorn sandbox.api:app --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT
sleep 2
$PY -m streamlit run ui/app.py --server.port 8501
