#!/usr/bin/env bash
# ============================================================================
# Foreman — ONE command: venv + deps + launch the agent UI.
#   ./run.sh
# Fill .env first (copy .env.example -> .env): GEMINI_API_KEY + MDB_MCP_CONNECTION_STRING.
# Needs Node/npx on PATH (the MongoDB MCP server is fetched on first run).
# ============================================================================
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "!! created .env from .env.example — open it and add GEMINI_API_KEY + MDB_MCP_CONNECTION_STRING"
fi

# Node check (the partner MCP server runs via npx)
if ! command -v npx >/dev/null 2>&1; then
  echo "!! npx not found — install Node.js (https://nodejs.org). The MongoDB MCP server needs it."
fi

echo "==> [1/2] python deps (venv .venv, one-time)"
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install -q -U pip wheel || true
python -m pip install -q -r requirements.txt

PORT="${PORT:-8011}"

# Free the port if a previous run left something bound to it (the npx MCP child
# can inherit the listening socket and keep it open). No more "address already in use".
free_port() {
  # `|| true` so a free port (fuser/lsof return non-zero when nothing's there)
  # doesn't trip `set -e` and kill the script.
  command -v fuser >/dev/null 2>&1 && fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
  command -v lsof  >/dev/null 2>&1 && lsof -ti "tcp:${PORT}" 2>/dev/null | xargs -r kill >/dev/null 2>&1 || true
  return 0
}
free_port; sleep 0.4

# On Ctrl+C / exit, stop uvicorn AND free the port so nothing lingers for next time.
cleanup() { trap - EXIT INT TERM; [ -n "${UPID:-}" ] && kill "$UPID" >/dev/null 2>&1; sleep 0.3; free_port; }
trap cleanup EXIT INT TERM

echo "==> [2/2] launch Foreman console  ->  http://127.0.0.1:${PORT}"
echo "    (agent runs in-process; MongoDB MCP fetched via npx on first run)"
echo "    enter an unsolved problem · Ctrl+C frees the port automatically"
# console.py serves web/console.html and runs root_agent (agent.py) via the ADK Runner.
# Run in the background (not exec) so the trap can clean up on Ctrl+C.
python -m uvicorn console:app --host 127.0.0.1 --port "${PORT}" &
UPID=$!
wait "$UPID"
