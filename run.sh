#!/usr/bin/env bash
# ============================================================================
# Renji Research Lab — ONE command: venv + deps + launch the agent UI.
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

echo "==> [2/2] launch the agent UI  ·  pick 'renji_research_lab'"
echo "    (ADK serves a local URL; the MongoDB MCP server is fetched via npx on first run)"
# `adk web` discovers the module-level root_agent in agent.py.
exec adk web
