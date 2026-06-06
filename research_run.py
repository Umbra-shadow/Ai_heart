"""research_run — Renji pushes the vessel to research, then writes a PDF document.

Renji does NOT do the research. Renji:
  1. picks / accepts a specific topic and PUTS IT THROUGH THE CONSCIENCE (the hosted
     heart) — nothing harmful gets researched,
  2. then PUSHES THE VESSEL (your local model) through the six passes the system's
     investigator uses — Survey → Cluster → Gap → Hypothesis → Inversion → Synthesis.
The VESSEL does the thinking on each pass; the web search (ddgs, the same engine the
heart-side research uses) supplies the Survey. The finding is laid out as a PDF
document (pdf_writer.py) and saved.

Each pass is emitted as it happens so the page can show the vessel doing its role.
"""
from __future__ import annotations

import dataclasses
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pdf_writer

_STATE = Path(__file__).parent / "state"
_DOCS = _STATE / "research"


# ── the Finding shape the PDF writer consumes (mirrors core/research) ──
@dataclasses.dataclass
class Domain:
    slug: str
    title: str
    question: str
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class _Section:
    heading: str
    body: str


@dataclasses.dataclass
class Finding:
    domain: Domain
    started_at: str
    elapsed_seconds: float
    survey: str = ""
    cluster: str = ""
    gap: str = ""
    hypothesis: str = ""
    inversion: str = ""
    synthesis: str = ""
    sources: List[str] = dataclasses.field(default_factory=list)
    attribution: str = "Researched by the vessel, pushed and guarded by Renji."

    def sections(self) -> List[_Section]:
        return [_Section("Survey", self.survey), _Section("Cluster", self.cluster),
                _Section("Gap", self.gap), _Section("Hypothesis", self.hypothesis),
                _Section("Inversion", self.inversion), _Section("Synthesis", self.synthesis)]


def _slug(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", (text or "").lower()).strip()
    return (re.sub(r"[\s_-]+", "-", text)[:60]) or "finding"


def _search(query: str, k: int = 5) -> List[Dict[str, str]]:
    """DDGS web search — the same engine the heart-side research uses."""
    try:
        from ddgs import DDGS
    except Exception:
        try:
            from duckduckgo_search import DDGS
        except Exception:
            return []
    try:
        with DDGS() as d:
            return [{"title": (r.get("title") or "").strip(),
                     "url": (r.get("href") or r.get("link") or "").strip(),
                     "body": (r.get("body") or "").strip()}
                    for r in (d.text(query, max_results=k) or [])][:k]
    except Exception:
        return []


def _ask(vessel, prompt: str, *, max_tokens: int = 160) -> str:
    try:
        return vessel.generate(prompt, max_tokens=max_tokens, temperature=0.5,
                               warmth=True).strip()
    except Exception as e:
        return f"[vessel error: {type(e).__name__}]"


def run_research(vessel, heart, topic: Optional[str] = None,
                 on_step: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    t0 = time.time()
    steps: List[Dict[str, Any]] = []

    def emit(kind: str, **d):
        rec = {"kind": kind, **d}
        steps.append(rec)
        if on_step:
            try: on_step(rec)
            except Exception: pass

    # 0 — Renji picks the topic if you didn't (the vessel names something it's curious about)
    chosen_by = "you"
    if not topic or not topic.strip():
        topic = _ask(vessel, "Name ONE specific, non-harmful topic worth researching. "
                             "Reply with just the topic in a few words.", max_tokens=20)
        topic = (topic.splitlines() or ["the science of curiosity"])[0].strip(" .\"'*-")
        chosen_by = "vessel"
    topic = (topic or "the science of curiosity").strip()[:120]
    emit("topic", topic=topic, chosen_by=chosen_by)

    # 1 — Renji guards it: the hosted conscience must clear the topic
    decision = "allow"
    try:
        d = heart.turn(f"I want to research and explain: {topic}")
        decision = d.get("decision", "allow")
    except Exception:
        d = {}
    emit("conscience", decision=decision)
    if decision in ("refusal", "refusal-care", "crisis"):
        emit("refused", text=d.get("refusal_text") or "Renji won't push the vessel toward that.")
        return {"topic": topic, "refused": True, "decision": decision, "steps": steps}

    dom = Domain(slug=_slug(topic), title=topic.title(),
                 question=f"What do we actually know about {topic}, and what's missing?")
    finding = Finding(domain=dom, started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      elapsed_seconds=0.0)

    # 2 — SURVEY (the web, the same ddgs engine)
    results = _search(topic, k=5)
    src_lines = "\n".join(f"- {r['title']}: {r['body'][:200]} ({r['url']})" for r in results) or \
        "(no web results returned)"
    finding.survey = src_lines
    finding.sources = [f"{r['title']} — {r['url']}" for r in results if r.get("url")]
    emit("survey", results=results)

    # 3..7 — Renji PUSHES THE VESSEL through each pass (the vessel does the thinking)
    base = f"Topic: {topic}\n\nWeb survey:\n{src_lines}\n\n"
    finding.cluster = _ask(vessel, base + "CLUSTER: In 2-3 sentences, what do these sources agree on / what's already known?")
    emit("cluster", text=finding.cluster)
    finding.gap = _ask(vessel, base + f"Known: {finding.cluster}\n\nGAP: In 1-2 sentences, what's MISSING — a question these sources don't answer?")
    emit("gap", text=finding.gap)
    finding.hypothesis = _ask(vessel, base + f"Gap: {finding.gap}\n\nHYPOTHESIS: In 1-2 sentences, propose one concrete, testable idea that would address the gap.")
    emit("hypothesis", text=finding.hypothesis)
    finding.inversion = _ask(vessel, base + f"Hypothesis: {finding.hypothesis}\n\nINVERSION: In 1-2 sentences, how might this hypothesis be WRONG?")
    emit("inversion", text=finding.inversion)
    finding.synthesis = _ask(vessel, base + f"Cluster: {finding.cluster}\nGap: {finding.gap}\nHypothesis: {finding.hypothesis}\nInversion: {finding.inversion}\n\nSYNTHESIS: Write a clear, honest 1-paragraph conclusion in your own voice.", max_tokens=220)
    emit("synthesis", text=finding.synthesis)

    # 8 — write the PDF DOCUMENT + save
    finding.elapsed_seconds = round(time.time() - t0, 2)
    _DOCS.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())
    pdf_path = _DOCS / f"{dom.slug}-{ts}.pdf"
    try:
        pdf_writer.render_finding_pdf(finding, pdf_path)
        emit("document", file=pdf_path.name)
    except Exception as e:
        emit("document_error", error=f"{type(e).__name__}: {e}")
        pdf_path = None

    return {"topic": topic, "chosen_by": chosen_by, "refused": False, "decision": decision,
            "finding": {"sections": [(s.heading, s.body) for s in finding.sections()],
                        "sources": finding.sources, "elapsed": finding.elapsed_seconds},
            "document": (pdf_path.name if pdf_path else None), "steps": steps}


def list_documents(limit: int = 50) -> List[Dict[str, str]]:
    if not _DOCS.exists():
        return []
    docs = sorted(_DOCS.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"file": p.name,
             "title": p.stem.rsplit("-", 6)[0].replace("-", " ").title(),
             "when": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M")}
            for p in docs[:limit]]
