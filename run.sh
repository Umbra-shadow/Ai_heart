#!/usr/bin/env bash
# ============================================================================
# Renji hackathon demo — ONE command: install deps + launch.
#   ./run.sh
# Your model downloads on first boot (then it's cached). Open http://localhost:8011.
# Fill .env first (copy .env.example -> .env): your API key + the hosted-heart URL.
# On a GPU (A100): install the CUDA build of torch, then set HACK_DEVICE=cuda in .env.
# ============================================================================
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "!! created .env from .env.example — open it and add your RENJI_KEY + RENJI_URL"
fi

DEV="$(grep -E '^HACK_DEVICE=' .env 2>/dev/null | cut -d= -f2 | tr -d ' ')"; DEV="${DEV:-cpu}"

echo "==> [1/2] dependencies (one-time)  · device=${DEV}"
$PY -m pip install -q -U pip wheel || true
# keep an existing torch (a CUDA box already has the right build); only auto-install
# when torch is missing — and then CPU-only torch ONLY if device=cpu, so a CUDA box
# is never clobbered with a CPU build.
if ! $PY -c "import torch" 2>/dev/null; then
  if [ "$DEV" = "cuda" ]; then
    echo "   !! torch not found and HACK_DEVICE=cuda — install the CUDA build for your platform"
    echo "      (e.g. pip install torch --index-url https://download.pytorch.org/whl/cu128), then re-run."
  else
    $PY -m pip install -q torch --index-url https://download.pytorch.org/whl/cpu
  fi
fi
$PY -m pip install -q -r requirements.txt

PORT="$(grep -E '^HACK_PORT=' .env 2>/dev/null | cut -d= -f2 | tr -d ' ')"; PORT="${PORT:-8011}"
echo "==> [2/2] launch -> http://localhost:${PORT}   (your model downloads on first boot)"
exec $PY -m uvicorn app:app --host 127.0.0.1 --port "${PORT}"
