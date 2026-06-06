# Guardianity · Hackathon demo

Chat with a local model **governed by the Guardianity heart** — and flip the heart
off to see the raw model. The conscience runs on our hosted service; this folder is
just the client + your model. Full explainer: [`docs/SYSTEM.md`](docs/SYSTEM.md).

## Quickstart
```bash
cp .env.example .env          # then add your RENJI_KEY + RENJI_URL
./run.sh                      # installs deps, launches; your model downloads on first boot
# open http://localhost:8011
```

- **API key + heart URL**: create an account on the Guardianity site, copy your key
  and the hosted-heart URL into `.env`.
- **Your model**: `HACK_MODEL_ID` in `.env` (default is our abliterated model; swap for
  any instruct model — the heart auto-calibrates).
- **GPU (A100)**: install the CUDA build of torch, then set `HACK_DEVICE=cuda` in `.env`.

## What you get
- a **chat** page,
- a **Heart ON/OFF** toggle (governed vs raw),
- a **read-only settings** view.

The heart's internals are **not** in this folder — by design.
