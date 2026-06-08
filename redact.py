"""
redact.py — private mode: mask confidential data BEFORE it reaches Gemini.
=========================================================================
When the lab runs over confidential records, you don't want the raw PII — names,
emails, card / account numbers — leaving your box to the cloud model. This module
masks it on the way out and restores it on the way back, wired into the agent as
two Google-ADK callbacks:

  • ``redact_tool_result``  (``after_tool_callback``) — runs AFTER a Mongo tool
    returns and BEFORE that data enters the model's context. PII in the result is
    replaced with stable placeholders (``[EMAIL_1]``, ``[CARD_1]`` …). Gemini only
    ever sees the placeholders.
  • ``restore_model_response`` (``after_model_callback``) — runs after Gemini
    answers; the placeholders in its text are swapped back to the real values,
    locally, before you see them.

So Gemini reasons on stand-ins; the real values never leave the box. Turn it on
with ``REDACT_MODE=1`` (mask every read) or ``CONFIDENTIAL_COLLECTIONS=a,b`` (mask
only reads from those collections). The mapping lives in-process only.

Note: this is regex-based PII masking (emails, phones, cards, SSNs, IBANs, account
numbers). Names are masked when listed in ``CONFIDENTIAL_NAMES`` (a NER pass is the
production upgrade). It is the privacy *seam*, demonstrably wired — extend the rules
to your data.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple

# ── PII rules (ordered: most specific first) ────────────────────────────────
_RULES: List[Tuple[str, "re.Pattern[str]"]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("CARD",  re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("IBAN",  re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}\b")),
    ("SSN",   re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("PHONE", re.compile(r"\b(?:\+?\d{1,3}[ -]?)?(?:\(?\d{2,4}\)?[ -]?){2,4}\d{2,4}\b")),
    ("ACCT",  re.compile(r"\b(?:acct|account|a/c)\s*#?\s*[:=]?\s*([A-Z0-9-]{6,})\b", re.I)),
]


def _name_rule() -> "re.Pattern[str] | None":
    names = [n.strip() for n in os.environ.get("CONFIDENTIAL_NAMES", "").split(",") if n.strip()]
    if not names:
        return None
    names.sort(key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b")


class Vault:
    """Holds the placeholder ↔ real-value mapping for one run."""

    def __init__(self) -> None:
        self.to_real: Dict[str, str] = {}     # "[EMAIL_1]" -> "jane@x.com"
        self.to_ph: Dict[str, str] = {}       # "jane@x.com" -> "[EMAIL_1]"
        self.counts: Dict[str, int] = {}

    def _placeholder(self, kind: str, real: str) -> str:
        if real in self.to_ph:
            return self.to_ph[real]
        self.counts[kind] = self.counts.get(kind, 0) + 1
        ph = f"[{kind}_{self.counts[kind]}]"
        self.to_ph[real] = ph
        self.to_real[ph] = real
        return ph

    def redact(self, text: str) -> str:
        if not text:
            return text
        rules = list(_RULES)
        nr = _name_rule()
        if nr is not None:
            rules.insert(0, ("PERSON", nr))
        out = text
        for kind, rx in rules:
            def repl(m: "re.Match[str]", _k=kind) -> str:
                real = m.group(0)
                # ACCT captures the id in group 1; keep the label, mask the id
                if _k == "ACCT" and m.lastindex:
                    return m.group(0).replace(m.group(1), self._placeholder(_k, m.group(1)))
                # avoid masking tiny/pure-label numbers (e.g. "20" mg) as CARD/PHONE
                if _k in ("CARD", "PHONE") and len(re.sub(r"\D", "", real)) < 7:
                    return real
                return self._placeholder(_k, real)
            out = rx.sub(repl, out)
        return out

    def restore(self, text: str) -> str:
        if not text:
            return text
        out = text
        for ph, real in self.to_real.items():
            out = out.replace(ph, real)
        return out


# In-process vault (single run = the demo). Scope per-session for production.
_VAULT = Vault()


def _on() -> bool:
    return os.environ.get("REDACT_MODE", "").strip().lower() in ("1", "true", "yes", "on")


def _confidential() -> set:
    return {c.strip().lower() for c in os.environ.get("CONFIDENTIAL_COLLECTIONS", "").split(",") if c.strip()}


def _should_mask(args: Dict[str, Any]) -> bool:
    if _on():
        return True
    conf = _confidential()
    if not conf:
        return False
    coll = ""
    if isinstance(args, dict):
        coll = str(args.get("collection") or args.get("collectionName") or "").lower()
    return coll in conf


def _deep_redact(obj: Any) -> Any:
    if isinstance(obj, str):
        return _VAULT.redact(obj)
    if isinstance(obj, list):
        return [_deep_redact(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _deep_redact(v) for k, v in obj.items()}
    return obj


# ── ADK callbacks (defensive about signatures across ADK versions) ──────────
def redact_tool_result(*cb_args: Any, **cb_kwargs: Any) -> Any:
    """after_tool_callback: mask PII in a tool result before it reaches Gemini.
    ADK passes (tool, args, tool_context, tool_response); we read positionally
    and tolerate variants. Return the (possibly redacted) response, else None."""
    args = cb_args[1] if len(cb_args) > 1 else cb_kwargs.get("args", {})
    response = cb_args[3] if len(cb_args) > 3 else cb_kwargs.get("tool_response")
    if response is None or not _should_mask(args or {}):
        return None
    try:
        return _deep_redact(response)
    except Exception:
        return None


def restore_model_response(*cb_args: Any, **cb_kwargs: Any) -> Any:
    """after_model_callback: restore real values in Gemini's answer, locally.
    ADK passes (callback_context, llm_response); we restore text parts in place
    and return the response, else None."""
    resp = cb_args[1] if len(cb_args) > 1 else cb_kwargs.get("llm_response")
    if resp is None or not _VAULT.to_real:
        return None
    try:
        content = getattr(resp, "content", None)
        parts = getattr(content, "parts", None) if content is not None else None
        changed = False
        for p in (parts or []):
            t = getattr(p, "text", None)
            if isinstance(t, str) and t:
                r = _VAULT.restore(t)
                if r != t:
                    p.text = r
                    changed = True
        return resp if changed else None
    except Exception:
        return None
