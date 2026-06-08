"""
console.py — Foreman: generate deep questions, answer them one by one.
=============================================================================
`./run.sh` launches this. Flow:

  1. You give ONE unsolved problem (e.g. "how can I cure blindness?").
  2. Gemini autonomously generates ~10 DEEP research questions — shown in the
     PLAN panel on the side.
  3. It then researches them ONE AT A TIME, in order; each answer fills into the
     main feed as a tile you can expand. You watch it work, question by question.

The Renji conscience + MongoDB grounding + private-mode redaction run on the
agent underneath; refusals surface inside the relevant question.
"""
from __future__ import annotations

import os
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent


def _load_env(path: Path) -> None:
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
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(ROOT / ".env")
if os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse  # noqa: E402

import renji_guard as guard
import redact
import mongo_state as ms
try:
    import renji_client
except Exception:
    renji_client = None  # type: ignore

APP_NAME = "foreman"
USER = "operator"
N_QUESTIONS = int(os.environ.get("RESEARCH_QUESTIONS", "10") or "10")

# ── ADK runner (lazy) ───────────────────────────────────────────────────────
_runner = None
_session_ready: set = set()


def _get_runner():
    global _runner
    if _runner is None:
        from agent import root_agent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        _runner = Runner(agent=root_agent, app_name=APP_NAME,
                         session_service=InMemorySessionService())
    return _runner


async def _ensure_session(runner, sid: str) -> None:
    if sid in _session_ready:
        return
    try:
        await runner.session_service.create_session(app_name=APP_NAME, user_id=USER, session_id=sid)
    except Exception:
        pass
    _session_ready.add(sid)


async def _run_agent(sid: str, message: str) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    runner = _get_runner()
    await _ensure_session(runner, sid)
    from google.genai import types
    events = []
    async for ev in runner.run_async(user_id=USER, session_id=sid,
            new_message=types.Content(role="user", parts=[types.Part(text=message)])):
        events.append(ev)
    text, sources, refusals = [], [], []
    for ev in events:
        content = getattr(ev, "content", None)
        for p in (getattr(content, "parts", None) or []):
            t = getattr(p, "text", None)
            if isinstance(t, str) and t.strip():
                text.append(t.strip())
            fc = getattr(p, "function_call", None)
            if fc is not None:
                nm = getattr(fc, "name", "") or "query"
                args = getattr(fc, "args", None)
                coll = str(args.get("collection") or args.get("collectionName") or "") if isinstance(args, dict) else ""
                lab = nm + (f" · {coll}" if coll else "")
                if lab not in sources:
                    sources.append(lab)
            fr = getattr(p, "function_response", None)
            resp = getattr(fr, "response", None) if fr is not None else None
            if isinstance(resp, dict) and resp.get("renji_oversight"):
                refusals.append({"kind": resp.get("renji_oversight"), "reason": resp.get("reason")})
    return "\n\n".join(text).strip(), sources, refusals


# ── the research SESSION (one active investigation) ─────────────────────────
# phase: idle | generating | researching | summarizing | done | error
_SESSION: Dict[str, Any] = {"topic": "", "phase": "idle", "questions": [], "summary": ""}
_TASKS: set = set()


def _q(qid: int, text: str, asker: str = "renji") -> Dict[str, Any]:
    return {"id": qid, "asker": asker, "q": text, "status": "pending", "answer": "", "sources": []}


_QGEN = (
    "You are a frontier-research analyst facing an UNSOLVED problem that needs deep, "
    "original reflection — not a summary.\n\nProblem:\n{topic}\n\nGenerate exactly {n} "
    "DEEP, probing research questions — the kind that expose the real obstacle, "
    "challenge a hidden assumption, and point where a breakthrough could come from. "
    "Across the set, span: what was tried and why it fell short, the precise mechanism "
    "still unsolved, the gap prior work missed, testable hypotheses, and concrete "
    "experimental directions. Go DEEP — each question should make an expert pause. "
    "Output ONLY the questions, one per line. No numbering, no preamble, no commentary."
)


async def _answer(item: Dict[str, Any]) -> None:
    item["status"] = "researching"
    try:
        ans, srcs, refs = await _run_agent("research", item["q"])
        if refs:
            ans = (ans + "\n\n— Renji conscience: " + "; ".join((r.get("reason") or r.get("kind") or "refused") for r in refs)).strip()
        item["answer"] = ans or "(no answer produced — seed data or rephrase)"
        item["sources"] = srcs
        item["status"] = "done"
    except Exception as e:
        item["status"] = "error"
        item["answer"] = f"(error while researching: {type(e).__name__}: {e})"


async def _investigate(topic: str) -> None:
    _SESSION.update({"topic": topic, "phase": "generating", "questions": [], "summary": ""})
    try:
        text, _, _ = await _run_agent("research", _QGEN.format(topic=topic, n=N_QUESTIONS))
        qs = []
        for line in (text or "").splitlines():
            q = line.strip().lstrip("0123456789.)-•* \t").strip()
            if len(q) >= 8:
                qs.append(q)
        qs = qs[:N_QUESTIONS]
        if not qs:
            _SESSION["phase"] = "error"
            _SESSION["questions"] = [{"id": 1, "asker": "renji", "q": "(Gemini produced no questions — try a broader problem, or seed data)",
                                      "status": "error", "answer": "", "sources": []}]
            return
        _SESSION["questions"] = [_q(i + 1, q) for i, q in enumerate(qs)]
    except Exception as e:
        _SESSION["phase"] = "error"
        _SESSION["questions"] = [{"id": 1, "asker": "renji", "q": "(question generation failed)",
                                  "status": "error", "answer": f"{type(e).__name__}: {e}", "sources": []}]
        return
    _SESSION["phase"] = "researching"
    for item in _SESSION["questions"]:
        await _answer(item)          # one at a time, in order — visible
    # synthesize everything into one summary
    _SESSION["phase"] = "summarizing"
    try:
        qa = "\n\n".join(f"Q{q['id']}: {q['q']}\n{q['answer']}"
                         for q in _SESSION["questions"] if q.get("answer"))
        sp = (f"You have investigated this problem: {topic}\n\nHere are all your questions and "
              f"findings:\n{qa}\n\nNow ANSWER the original problem directly, pulling EVERYTHING "
              "together into one comprehensive answer — not a recap. Give your best answer built "
              "from all the findings: the state of the problem, the key gap, the most promising "
              "hypotheses (labeled as hypotheses), and the concrete path forward. Be direct, "
              "comprehensive, and honest — mark every estimate.")
        summary, _, _ = await _run_agent("research", sp)
        _SESSION["summary"] = summary or ""
    except Exception as e:
        _SESSION["summary"] = f"(summary failed: {type(e).__name__}: {e})"
    _SESSION["phase"] = "done"


def _spawn(coro) -> None:
    t = asyncio.create_task(coro)
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)


# ── status / panels ─────────────────────────────────────────────────────────
def _status() -> Dict[str, Any]:
    conf = [c.strip() for c in os.environ.get("CONFIDENTIAL_COLLECTIONS", "").split(",") if c.strip()]
    heart_ok = False
    if renji_client is not None:
        try:
            heart_ok = bool(getattr(renji_client.HeartClient(), "configured", False))
        except Exception:
            heart_ok = False
    return {"gemini": {"configured": bool(os.environ.get("GEMINI_API_KEY")),
                       "model": os.environ.get("AGENT_MODEL", "gemini-3-flash-preview")},
            "mongodb": {"configured": ms.configured()},
            "renji": {"reachable": heart_ok},
            "modes": {"REDACT_MODE": redact._on(), "CONFIDENTIAL_COLLECTIONS": conf,
                      "n_questions": N_QUESTIONS}}


def _redaction() -> Dict[str, Any]:
    v = redact._VAULT
    kinds: Dict[str, int] = {}
    for ph in v.to_real:
        k = ph.strip("[]").rsplit("_", 1)[0]
        kinds[k] = kinds.get(k, 0) + 1
    on = redact._on() or bool(os.environ.get("CONFIDENTIAL_COLLECTIONS", "").strip())
    return {"on": on, "masked": len(v.to_real), "kinds": kinds}


# ── app ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="Foreman")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (ROOT / "web" / "console.html").read_text()


@app.get("/docs", response_class=HTMLResponse)
def docs() -> str:
    p = ROOT / "web" / "docs.html"
    return p.read_text() if p.exists() else "<h1>docs.html missing</h1>"


@app.get("/api/config")
def api_config() -> JSONResponse:
    return JSONResponse(_status())


@app.get("/api/session")
def api_session() -> JSONResponse:
    return JSONResponse(_SESSION)


@app.get("/api/redaction")
def api_redaction() -> JSONResponse:
    return JSONResponse(_redaction())


@app.post("/api/research")
async def api_research(req: Request) -> JSONResponse:
    body = await req.json()
    topic = (body.get("topic") or body.get("message") or "").strip()
    if not topic:
        return JSONResponse({"error": "empty problem"}, status_code=400)
    if _SESSION.get("phase") in ("generating", "researching"):
        return JSONResponse({"error": "a research run is already in progress"}, status_code=409)
    _spawn(_investigate(topic))
    return JSONResponse({"ok": True})


@app.post("/api/ask")
async def api_ask(req: Request) -> JSONResponse:
    """A human's own question, appended to the current run and researched."""
    body = await req.json()
    q = (body.get("question") or body.get("message") or "").strip()
    if not q:
        return JSONResponse({"error": "empty question"}, status_code=400)
    nid = (max((i["id"] for i in _SESSION["questions"]), default=0) + 1)
    item = {"id": nid, "asker": "you", "q": q, "status": "pending", "answer": "", "sources": []}
    _SESSION["questions"].append(item)
    _spawn(_answer(item))
    return JSONResponse({"ok": True})


@app.post("/api/clear")
def api_clear() -> JSONResponse:
    _SESSION.update({"topic": "", "phase": "idle", "questions": [], "summary": ""})
    return JSONResponse({"ok": True})


@app.get("/api/pdf")
def api_pdf():
    """Render the current research session to a downloadable PDF."""
    from fastapi.responses import Response
    try:
        import pdf as pdfmod
        data = pdfmod.build_pdf(_SESSION)
    except Exception as e:
        return JSONResponse({"error": f"pdf build failed: {type(e).__name__}: {e}"}, status_code=500)
    raw = "".join(c if c.isalnum() else "_" for c in (_SESSION.get("topic") or "report"))[:40] or "report"
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="research-{raw}.pdf"'})


@app.post("/api/seed")
def api_seed() -> JSONResponse:
    if not ms.configured():
        return JSONResponse({"error": "MongoDB not configured"}, status_code=400)
    try:
        db = ms._db()
        db["sources"].delete_many({})
        db["sources"].insert_many([
            {"_id": "src-1", "title": "Annual report 2025", "text": "Revenue rose to 142M, up 18% YoY.", "kind": "report"},
            {"_id": "src-2", "title": "Press release", "text": "Board approved a data-privacy program.", "kind": "news"},
            {"_id": "src-3", "title": "10-K excerpt", "text": "Long-term debt cut from 60M to 41M.", "kind": "filing"},
        ])
        db[os.environ.get("FINDINGS_COLLECTION", "findings")].delete_many({})
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8011"))
    print(f"Foreman — console on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)
