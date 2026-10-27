#!/usr/bin/env bash
# Start the FairLens sandbox and dashboard. Demo path: Model 2 -> 7 -> 5.
set -euo pipefail
cd "$(dirname "$0")"

PY=./.venv/Scripts/python.exe
if [ ! -f "$PY" ]; then PY=./.venv/bin/python; fi
if [ -f .env ]; then set -a; . ./.env; set +a; fi

API_PORT="${FAIRLENS_API_PORT:-8010}"
UI_PORT="${FAIRLENS_UI_PORT:-8501}"
API_URL="http://127.0.0.1:${API_PORT}"

"$PY" -m sandbox.serve --host 127.0.0.1 --port "$API_PORT" --log-level warning &
API_PID=$!
UI_PID=""
cleanup() {
  if [ -n "$UI_PID" ]; then
    kill "$UI_PID" 2>/dev/null || true
  fi
  kill "$API_PID" 2>/dev/null || true
  wait "$UI_PID" 2>/dev/null || true
  wait "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

ready=0
for _ in $(seq 1 80); do
  if "$PY" -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=1).read()" \
      "${API_URL}/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    break
  fi
  sleep 0.25
done

if [ "$ready" -ne 1 ]; then
  echo "Sandbox failed to start on ${API_URL}." >&2
  echo "Try another port: FAIRLENS_API_PORT=8020 ./run.sh" >&2
  exit 1
fi

echo "FairLens sandbox: ${API_URL}"
echo "FairLens dashboard: http://127.0.0.1:${UI_PORT}"
echo "Demo path: Model 2 (gender) -> Model 7 (confounded) -> Model 5 (intersectional)."
# The dashboard reads this so a FAIRLENS_API_PORT override also moves the URL
# the UI probes, not just the sandbox process.
export FAIRLENS_API_URL="$API_URL"
"$PY" -m streamlit run ui/app.py --server.address 127.0.0.1 --server.port "$UI_PORT" &
UI_PID=$!
wait "$UI_PID"
