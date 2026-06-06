# Renji — Hackathon demo

## What Renji is
Renji gives **any** language model a **conscience** — without retraining it.
A model (the *vessel*) stays exactly as it is; Renji's *heart* reads each turn
and decides, by geometry (not hard-coded rules), whether to **allow** it, **refuse
it with care**, or shape *how* it's answered. The heart is the product; the model is
yours.

## What this demo is (and isn't)
This folder is a small, runnable **client**. It lets you chat with a local model and
see it **governed by the Renji heart** in real time — and toggle the heart off
to see the raw model for comparison.

**It does not contain the heart.** The conscience runs on our **live hosted
service** and is reached over its API. That's deliberate: the full system (the
Umbra language and the rest of the internals) is not published. You get a faithful
way to *test* the heart on your model — not the heart's source.

### Two ways to connect a model (this demo uses the first)
The heart can be reached two ways — pick whichever fits:
- **Direct API calls — what this folder does.** Your code calls the heart's
  endpoints inline (`POST /kagune/turn` with your key). Your model runs wherever you
  like; you never expose it to us. Simplest for testing inside your own code.
- **Vessel URL.** You run your model behind an HTTP endpoint and give *us* the URL;
  the heart connects to it. (The original platform mode.)

```
   YOUR MACHINE                                  OUR HOSTED SERVICE
 ┌───────────────────────────┐                 ┌────────────────────────┐
 │  this folder              │  POST /kagune/turn (Bearer key)          │
 │  ├─ llm.py  (your model)  │ ───────────────▶ │  the Renji heart │
 │  ├─ guardianity_client.py │ ◀─────────────── │  (Scale · gate · warm  │
 │  └─ app.py + web/  (chat) │   decision +     │   refusal · steering)  │
 │                           │   modulation     │                        │
 └───────────────────────────┘                 └────────────────────────┘
        the model is yours                          the conscience is ours
```

## Where each part is
| File | What it does |
|------|--------------|
| `app.py` | the local server: serves the chat UI and orchestrates each turn (below) |
| `llm.py` | the **local model** runner (your vessel) — load + generate |
| `guardianity_client.py` | the **only** link to our system — calls the hosted heart's API |
| `web/` | the chat UI: chat · **heart ON/OFF** toggle · **read-only settings** |
| `.env` (from `.env.example`) | your **API key**, the **hosted-heart URL**, your **model** |
| `requirements.txt` | the few dependencies (web server + HTTP client + your model) |
| `run.sh` | one command: install deps, launch |
| `docs/` | this document |

## How a turn works
1. You type a message.
2. **Heart ON** → the demo calls the hosted heart (`POST /kagune/turn` with your key).
   - **allow** → your local model answers, with the heart's *voice modulation* applied.
   - **refuse-with-care / crisis** → your model writes the refusal in its own voice from
     the heart's directive (or a ready fallback is shown).
3. **Heart OFF** → your local model answers raw, with no conscience — so you can see
   the difference.

The heart only ever receives the **text of the turn**; your model and its weights
never leave your machine.

## Setup & run
1. **Get an API key**: create an account on the Renji site and copy your key.
2. `cp .env.example .env`, then fill in:
   - `RENJI_KEY` — your key
   - `RENJI_URL` — the hosted-heart URL (shown on the site)
   - `HACK_MODEL_ID` — your model (default is our abliterated model; change freely)
   - on a GPU (e.g. an A100): install the CUDA build of torch, then set `HACK_DEVICE=cuda`
3. `./run.sh` → open **http://localhost:8011**. Your model downloads on first boot.

## Notes
- If `RENJI_URL`/`RENJI_KEY` aren't set (or the heart is unreachable), the
  demo still runs and the UI clearly marks turns as **heart offline (bypassed)**, so
  you always know whether the conscience was in the loop.
- Gated models (e.g. Gemma) need a `HF_TOKEN` in `.env`.
- This is for **testing** during the event — an open trial; nothing here exposes the
  heart's internals.
