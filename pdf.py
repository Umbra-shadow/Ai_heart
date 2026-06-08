"""
pdf.py — render a research session to a downloadable PDF report.
================================================================
Takes the in-memory research session (topic + answer + the 10 Q&A) and produces
a single PDF: title, the synthesized answer, then every question with its
findings and the sources it queried. Pure-python (fpdf2), no system deps.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from fpdf import FPDF

# Core PDF fonts are latin-1; map the common unicode the model emits, drop the rest.
_REP = {"—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "•": "-",
        "→": "->", "×": "x", "≈": "~", "…": "...", "≥": ">=", "≤": "<=", "·": "-"}


def _s(txt: Any) -> str:
    if txt is None:
        return ""
    t = str(txt)
    for k, v in _REP.items():
        t = t.replace(k, v)
    # strip control chars that break line-breaking, then force latin-1
    t = "".join(ch for ch in t if ch == "\n" or ch >= " ")
    return t.encode("latin-1", "replace").decode("latin-1")


def build_pdf(session: Dict[str, Any]) -> bytes:
    topic = session.get("topic") or "Research report"
    answer = session.get("summary") or ""          # the final "everything together" answer
    questions = session.get("questions") or []

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)
    pdf.add_page()
    W = pdf.epw                                     # effective page width (margins applied)

    def line(text: str, h: float = 6, size: float = 11, style: str = "", color=(0, 0, 0)) -> None:
        pdf.set_font("Helvetica", style, size)
        pdf.set_text_color(*color)
        pdf.set_x(pdf.l_margin)                      # always start at the left margin → full width
        txt = _s(text) or " "
        try:
            pdf.multi_cell(W, h, txt)
        except Exception:                            # never let one bad line kill the report
            try:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(W, h, txt.replace("  ", " ")[:1200] or " ")
            except Exception:
                pass
        pdf.set_text_color(0, 0, 0)

    line(topic, 9, 20, "B")
    line("Foreman  -  Gemini 3 + MongoDB + the Renji conscience  -  "
         + datetime.now().strftime("%Y-%m-%d %H:%M"), 5, 9, "", (120, 120, 120))
    pdf.ln(4)

    if answer:
        line("Answer", 8, 14, "B")
        pdf.ln(1)
        line(answer, 6, 11)
        pdf.ln(5)

    line("Questions & findings", 8, 14, "B")
    pdf.ln(2)
    for q in questions:
        who = "Your question" if q.get("asker") == "you" else ("Q" + str(q.get("id")))
        line(f"{who}.  {q.get('q', '')}", 6, 11, "B")
        pdf.ln(0.5)
        line(q.get("answer") or "(no answer)", 5.5, 10.5)
        srcs = q.get("sources") or []
        if srcs:
            line("queried: " + "   -   ".join(str(s) for s in srcs), 5, 9, "I", (80, 110, 80))
        pdf.ln(4)

    pdf.ln(6)
    line("Made by Guardianity   -   contact: balingenensiidan@gmail.com", 5, 9, "", (120, 120, 120))
    return bytes(pdf.output())
