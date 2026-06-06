"""pdf_writer — render a deep-research Finding to a PDF DOCUMENT.

The research artifact is a document: a title, the seed question Renji pushed the
vessel toward, the vessel's findings as labelled sections, and the sources. Renji
does NOT write the findings — the LLM does, steered by Renji onto a specific,
non-harmful question; this just lays the vessel's output out as a clean PDF.

Pure Python (fpdf2), no system dependencies. House style from the old HTML writer:
cream page, brown accents (#6b4423), quiet footer. Unicode-safe (registers a TTF
if present, else core font + sanitise) and long-URL-safe (breaks unbreakable runs).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_BROWN = (107, 68, 35)     # #6b4423
_INK = (28, 28, 28)        # #1c1c1c
_GREY = (119, 119, 119)    # #777
_RULE = (221, 221, 221)    # #ddd

_TTF_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _xy():
    """Return (XPos.LMARGIN, YPos.NEXT) so each block starts at the left margin."""
    try:
        from fpdf.enums import XPos, YPos
        return XPos.LMARGIN, YPos.NEXT
    except Exception:
        return "LMARGIN", "NEXT"


def _make_pdf():
    from fpdf import FPDF

    class _Doc(FPDF):
        uni = False
        fam = "Helvetica"

        def footer(self):
            self.set_y(-14)
            self.set_font(self.fam, "", 8)
            self.set_text_color(*_GREY)
            self.cell(0, 8, _safe(self, f"Renji · Deep Research · page {self.page_no()}"),
                      align="C")

    pdf = _Doc()
    reg = next((p for p in _TTF_CANDIDATES if os.path.exists(p)), None)
    if reg:
        try:
            bold = reg.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
            pdf.add_font("Body", "", reg)
            pdf.add_font("Body", "B", bold if os.path.exists(bold) else reg)
            pdf.add_font("Body", "I", reg)
            pdf.uni, pdf.fam = True, "Body"
        except Exception:
            pdf.uni, pdf.fam = False, "Helvetica"
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_margins(20, 20, 20)
    return pdf


def _safe(pdf, text: str) -> str:
    text = "" if text is None else str(text)
    if not getattr(pdf, "uni", False):
        text = text.encode("latin-1", "replace").decode("latin-1")
    return text


def _wrap_long(text: str, n: int = 72) -> str:
    """Insert breaks into unbreakable runs (long URLs) so multi_cell can wrap."""
    out = []
    for word in (text or "").replace("\r", "").split(" "):
        while len(word) > n:
            out.append(word[:n])
            word = word[n:]
        out.append(word)
    return " ".join(out)


def _block(pdf, text: str, size: float, style: str = "", color=_INK, lh: float = 0.6):
    nx, ny = _xy()
    pdf.set_font(pdf.fam, style, size)
    pdf.set_text_color(*color)
    pdf.multi_cell(0, size * lh, _wrap_long(_safe(pdf, text)), new_x=nx, new_y=ny)


def _heading(pdf, text: str, size: int = 13, top: float = 4):
    pdf.ln(top)
    _block(pdf, text, size, style="B", color=_BROWN, lh=0.6)


def render_finding_pdf(finding: Any, out_path) -> Path:
    """Render a deep_research.Finding into a PDF document at `out_path`."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = _make_pdf()
    # Document metadata — the saved file carries a real title + author.
    try:
        pdf.set_title(str(finding.domain.title)[:120])
        pdf.set_author("Renji")
        pdf.set_creator("Renji · Deep Research")
        pdf.set_subject(str(finding.domain.question)[:200])
    except Exception:
        pass
    pdf.add_page()

    _block(pdf, finding.domain.title, 22, style="B", color=_BROWN, lh=0.62)
    y = pdf.get_y() + 1
    pdf.set_draw_color(*_RULE)
    pdf.line(20, y, 190, y)
    pdf.ln(4)

    _block(pdf, f"Domain: {finding.domain.slug}    Started: {finding.started_at}"
                f"    Elapsed: {finding.elapsed_seconds:.2f}s", 9, color=_GREY)
    pdf.ln(1)
    _block(pdf, finding.attribution, 10, style="I", color=_INK)

    _heading(pdf, "Seed question (what Renji pushed the vessel toward)")
    _block(pdf, finding.domain.question, 11)
    for s in finding.sections():
        _heading(pdf, s.heading)
        _block(pdf, s.body, 11)

    _heading(pdf, "Sources")
    for src in (finding.sources or []):
        _block(pdf, f"•  {src}", 9, color=_GREY)

    pdf.output(str(out_path))
    return out_path
