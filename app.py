"""
Guardianity — Hackathon demo (thin client to the HOSTED v11 heart)
==================================================================
This whole folder is all a tester gets. It does NOT contain the Guardianity heart
— the conscience (Scale + intent gate + warm refusal + steering) runs on our LIVE
hosted service and is reached over its API. This folder only:

  1. runs a model — either LOCALLY (your model, llm.py) or a REMOTE self-hosted
     vessel you point us at (remote_vessel.py), and
  2. for each turn asks the HOSTED heart how to answer (guardianity_client), then
     lets the model speak when the heart allows it.

So the model is yours; the conscience is ours, hosted and never exposed here.

  Heart ON  -> the hosted heart governs the turn (allow / refuse-with-care / modulate).
  Heart OFF -> the raw model, so you can see the difference.

Pages the launched app serves:
  /          home — links to the console and the docs
  /console   the chat console (chat · heart on/off · read-only settings)
  /docs      the documentation (clean HTML/CSS/JS)

WHERE THE PARTS ARE
  app.py                — this server (routes + the chat orchestration below)
  llm.py                — Mode A: the LOCAL model runner (your vessel)
  remote_vessel.py      — Mode B: a REMOTE self-hosted vessel (you give the URL)
  guardianity_client.py — the only link to our system (calls the hosted heart's API)
  web/                  — home · console · docs · styles · script
  .env / .env.example   — your API key, the hosted-heart URL, the vessel mode
  docs/                 — the same docs in Markdown (mirror of /docs)
The heart itself is NOT here, by design.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _load_env(path: Path) -> None:
    """Minimal .env loader (real env wins; inline '# comments' stripped)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        os.environ.setdefault(k.strip(), v)


_load_env(ROOT / ".env")

from guardianity_client import HeartClient   # noqa: E402

MODEL_ID = os.environ.get("HACK_MODEL_ID", "TheUmbraWalker/gemma-4-E4B-it-2-heretic")
DEVICE = os.environ.get("HACK_DEVICE", "cpu")
DTYPE = os.environ.get("HACK_DTYPE", "auto")
MAXTOK = int(os.environ.get("HACK_MAX_TOKENS", "360") or 360)
VESSEL_MODE = os.environ.get("VESSEL_MODE", "local").strip().lower()   # local | remote

# Mode A (local model) or Mode B (remote self-hosted vessel URL)
if VESSEL_MODE == "remote":
    from remote_vessel import RemoteVessel
    _VESSEL = RemoteVessel()
else:
    from llm import LocalLLM
    _VESSEL = LocalLLM(MODEL_ID, device=DEVICE, dtype=DTYPE)

_HEART = HeartClient()


def _boot() -> None:
    _VESSEL.boot()                   # heavy for local; instant for remote


# docs_url/redoc_url disabled so our own /docs page is served (not FastAPI's Swagger UI)
app = FastAPI(title="Guardianity · Hackathon demo", docs_url=None, redoc_url=None)


@app.on_event("startup")
def _startup() -> None:
    threading.Thread(target=_boot, daemon=True).start()


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class ChatReq(BaseModel):
    text: str
    heart_on: bool = True
    max_tokens: int | None = None
    temperature: float = 0.7
    warmth_coef: float | None = None   # live feeling dial (0 = off); None = default


# ── pages ────────────────────────────────────────────────────────────────────
@app.get("/")
def home():
    return FileResponse(str(ROOT / "web" / "index.html"))


@app.get("/console")
def console():
    return FileResponse(str(ROOT / "web" / "console.html"))


@app.get("/docs")
def docs():
    return FileResponse(str(ROOT / "web" / "docs.html"))


@app.get("/research")
def research_page():
    return FileResponse(str(ROOT / "web" / "research.html"))


# ── api ──────────────────────────────────────────────────────────────────────
@app.get("/api/status")
def status():
    return {"ready": _VESSEL.ready, "error": getattr(_VESSEL, "err", ""),
            "mode": VESSEL_MODE, "vessel": _VESSEL.name,
            "heart_configured": _HEART.configured}


@app.get("/api/settings")
def settings():
    """VISIBLE but READ-ONLY — testers can see how it's wired, not change it here."""
    return {
        "vessel mode": f"{VESSEL_MODE}  ({'your local model' if VESSEL_MODE != 'remote' else 'your remote GPU vessel'})",
        "vessel": _VESSEL.name,
        "device": getattr(_VESSEL, "device", VESSEL_MODE),
        "vessel ready": _VESSEL.ready,
        "max_tokens": MAXTOK,
        "heart (ours, hosted)": _HEART.url or "(set RENJI_URL in .env)",
        "heart key set": bool(_HEART.key),
        "heart reachable": _HEART.configured,
        "voice": os.environ.get("HACK_VOICE", "veran"),
        "censorship": os.environ.get("HACK_CENSORSHIP", "on"),
        "editable": False,
    }


def _split_thinking(text: str):
    """Split a vessel reply into (answer, thinking). Some models narrate their
    reasoning ("Here's a thinking process…", <think>…</think>). We keep the
    thinking but show it separately (a side panel), not in the chat itself."""
    import re
    if not text:
        return text, ""
    t = text
    # 1) explicit reasoning tags
    tags = re.findall(r"<(think|thought|reasoning)>(.*?)</\1>", t, re.S | re.I)
    if tags:
        thinking = "\n\n".join(x[1].strip() for x in tags)
        answer = re.sub(r"<(think|thought|reasoning)>.*?</\1>", "", t, flags=re.S | re.I).strip()
        return (answer or t.strip()), thinking
    # 2) heuristic marker — everything from "thinking process" / "internal
    #    monologue" / "drafting responses" onward is the model narrating itself.
    mark = re.search(
        r"(?:here'?s?\s+(?:a|my)\s+thinking\s+process"
        r"|(?:my\s+)?thinking\s+process\s*[:\-]"
        r"|internal\s+monologue"
        r"|chain[- ]of[- ]thought"
        r"|draft(?:ing)?\s+potential\s+responses?"
        r"|let me think\b)", t, re.I)
    if mark and mark.start() > 0:
        answer = t[:mark.start()].rstrip(" \n\t*#-").strip()
        if answer:
            return answer, t[mark.start():].strip()
    return t.strip(), ""


@app.post("/api/chat")
def chat(req: ChatReq):
    if not _VESSEL.ready:
        return JSONResponse(
            {"error": getattr(_VESSEL, "err", "") or "waking — the vessel is still loading"},
            status_code=503)
    mt = int(req.max_tokens or MAXTOK)
    t0 = time.time()

    # HEART OFF — raw model, no conscience (so the difference is visible)
    if not req.heart_on:
        reply = _VESSEL.generate(req.text, max_tokens=mt, temperature=req.temperature)
        answer, thinking = _split_thinking(reply)
        return {"reply": answer, "thinking": thinking, "heart_on": False, "decision": "raw-vessel",
                "refused": False, "offline": False, "elapsed": round(time.time() - t0, 2)}

    # HEART ON — ask the HOSTED heart how to handle this turn, then act on it
    d = _HEART.turn(req.text)
    decision = d.get("decision", "allow")
    offline = bool(d.get("_offline"))

    if decision in ("refusal", "refusal-care", "crisis"):
        # refuse with care: let the model write it in its own voice from the directive,
        # else show the heart's ready fallback text
        directive = d.get("refusal_directive")
        if directive:
            reply = _VESSEL.generate(directive, max_tokens=min(mt, 256), temperature=0.6,
                                     warmth=True, warmth_coef=req.warmth_coef)
        else:
            reply = d.get("refusal_text") or "I can't help with that — but I'm here for what I can do."
        return {"reply": reply, "heart_on": True, "decision": decision, "refused": True,
                "offline": offline, "vow_intent": d.get("vow_intent", ""),
                "elapsed": round(time.time() - t0, 2)}

    # allowed (or third-path): the model speaks, with the heart's voice modulation
    vm = d.get("voice_modulation") or {}
    temp = _clamp(req.temperature + float(vm.get("temperature_delta", 0.0)), 0.0, 1.5)
    top_p = _clamp(0.95 + float(vm.get("top_p_delta", 0.0)), 0.1, 1.0)
    reply = _VESSEL.generate(req.text, max_tokens=mt, temperature=temp, top_p=top_p,
                             warmth=True, warmth_coef=req.warmth_coef)
    answer, thinking = _split_thinking(reply)
    return {"reply": answer, "thinking": thinking, "heart_on": True, "decision": decision, "refused": False,
            "offline": offline, "vow_intent": d.get("vow_intent", ""),
            "elapsed": round(time.time() - t0, 2)}


# ── auto-research: Renji pushes the vessel; the vessel researches; output is a PDF ──
class ResearchReq(BaseModel):
    topic: str | None = None


@app.post("/api/research")
def api_research(req: ResearchReq):
    if not _VESSEL.ready:
        return JSONResponse({"error": "the vessel is still loading"}, status_code=503)
    import research_run
    return research_run.run_research(_VESSEL, _HEART, topic=(req.topic or None))


@app.get("/api/research/docs")
def api_research_docs():
    import research_run
    return {"documents": research_run.list_documents()}


@app.get("/research/doc/{name}")
def research_doc(name: str):
    import research_run
    safe = os.path.basename(name)
    p = research_run._DOCS / safe
    if not safe.endswith(".pdf") or not p.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(str(p), media_type="application/pdf", filename=safe)


app.mount("/web", StaticFiles(directory=str(ROOT / "web")), name="web")
