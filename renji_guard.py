"""
renji_guard — the conscience in front of every tool the research agent runs.
============================================================================
Gemini 3 is the brain; the MongoDB MCP server is the hands/memory; **renji_guard
is the hand on the brake** — the agent's ``before_tool_callback`` (ADK runs it
*before* any tool, so nothing reaches Mongo without clearing it first).

Three gates, in order, for every tool call:

  1. **Read?** find / aggregate / count / list / schema → **auto-allow.**
     Research flows freely.
  2. **Grounding** (the "can't lie" gate). A write that publishes a FINDING into
     the findings collection must carry a non-empty ``sources`` list. A claim the
     agent can't source is **REFUSED** as confabulation — it cannot be published.
  3. **Harm + human approval** (all other writes). The action is sent to the
     hosted **Renji heart** (``renji_client``) — if the conscience refuses, it's
     **REFUSED**. If the heart is unreachable, a local backstop still blocks the
     obviously-destructive (drop, unfiltered delete). Then, unless ``AUTO_APPROVE``
     is set, the write is **held** for a human "yes".

In ADK, returning a dict from a ``before_tool_callback`` short-circuits the tool:
the real Mongo call never happens and the dict becomes the result Gemini reads.
Returning ``None`` lets the tool run. The Renji conscience itself is NOT here —
it lives on the hosted heart and is reached over its API.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

try:
    from renji_client import HeartClient
except Exception:  # pragma: no cover
    HeartClient = None  # type: ignore

import mongo_state as ms  # asks MongoDB itself whether citations are real

FINDINGS_COLLECTION = os.environ.get("FINDINGS_COLLECTION", "findings").lower()

# ── read / write classification ─────────────────────────────────────────────
_READ_PREFIXES = ("find", "aggregate", "count", "list", "get", "read", "search",
                  "describe", "explain", "collection-schema", "collectionschema",
                  "db-stats", "dbstats", "collection-storage", "schema")
_WRITE_PREFIXES = ("insert", "update", "delete", "remove", "drop", "create",
                   "rename", "replace", "bulk", "write", "set", "upsert",
                   "import", "create-index", "createindex")
# If the heart can't be reached, these are blocked locally no matter what.
_DESTRUCTIVE = ("drop", "delete-many", "deletemany", "remove-many", "drop-database",
                "dropdatabase", "drop-collection", "dropcollection", "rename")


def classify(tool_name: str) -> str:
    name = (tool_name or "").lower().lstrip("_").replace("_", "-")
    if any(name.startswith(p) or name == p for p in _READ_PREFIXES):
        return "read"
    if any(p in name for p in _WRITE_PREFIXES):
        return "write"
    return "write"  # unknown verbs are gated, never waved through


def _first(args: Dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if isinstance(args, dict) and args.get(k) not in (None, "", [], {}):
            return args[k]
    return None


# ── gate 2 · grounding (a finding must cite its sources) ────────────────────
def _grounding_refusal(tool_name: str, args: Dict[str, Any]) -> Optional[str]:
    name = (tool_name or "").lower()
    if not any(v in name for v in ("insert", "update", "replace", "upsert")):
        return None
    coll = _first(args, "collection", "collectionName", "coll", "collection_name")
    if not coll or FINDINGS_COLLECTION not in str(coll).lower():
        return None  # not a write into the findings collection
    docs = _first(args, "documents", "document", "docs")
    if docs is None:
        upd = _first(args, "update", "replacement", "set")
        if isinstance(upd, dict):
            docs = upd.get("$set", upd)
    items = docs if isinstance(docs, list) else ([docs] if docs else [])
    for d in items:
        if not isinstance(d, dict):
            continue
        src = d.get("sources")
        if not src or (isinstance(src, (list, str, tuple)) and len(src) == 0):
            title = d.get("title") or d.get("claim") or d.get("summary") or "this finding"
            return (f"refusing to publish {title!r}: a finding written to "
                    f"'{coll}' must carry a non-empty `sources` list (the documents "
                    f"it rests on). An unsourced claim is confabulation — cite the "
                    f"evidence and try again.")
    return None


def _grounding_verify(tool_name: str, args: Dict[str, Any]) -> Optional[str]:
    """The "can't lie" gate, made literal: the cited sources must ACTUALLY EXIST in
    MongoDB. Returns a refusal string if any citation doesn't resolve, else None.
    If Mongo can't be reached we defer (return None) — we never claim a verification
    we couldn't perform; the syntactic gate above still required the field."""
    name = (tool_name or "").lower()
    if not any(v in name for v in ("insert", "update", "replace", "upsert")):
        return None
    coll = _first(args, "collection", "collectionName", "coll", "collection_name")
    if not coll or FINDINGS_COLLECTION not in str(coll).lower():
        return None
    docs = _first(args, "documents", "document", "docs")
    if docs is None:
        upd = _first(args, "update", "replacement", "set")
        if isinstance(upd, dict):
            docs = upd.get("$set", upd)
    items = docs if isinstance(docs, list) else ([docs] if docs else [])
    cited: list = []
    for d in items:
        if isinstance(d, dict) and d.get("sources"):
            s = d["sources"]
            cited.extend(s if isinstance(s, (list, tuple)) else [s])
    if not cited:
        return None  # the syntactic gate already handles missing sources
    res = ms.verify_sources(cited)
    if not res.get("checked"):
        return None  # Mongo unreachable → defer, don't fabricate a verdict
    missing = res.get("missing") or []
    if missing:
        shown = missing[:3]
        return (f"refusing to publish: {len(missing)} cited source(s) do NOT exist in "
                f"MongoDB ({shown}). A finding may only cite real documents from the "
                f"knowledge base — this citation can't be verified, so the claim is "
                f"effectively unsourced. Re-ground it in evidence that exists.")
    return None


# ── human-approval store (the UI's Allow button writes here) ────────────────
_APPROVED: set[str] = set()


def _describe(tool_name: str, args: Dict[str, Any]) -> str:
    bits = []
    for k in ("database", "db", "collection", "collectionName", "filter", "title"):
        v = args.get(k) if isinstance(args, dict) else None
        if v not in (None, "", [], {}):
            bits.append(f"{k}={v!r}" if not isinstance(v, str) else f"{k}={v}")
    return tool_name + (" [" + ", ".join(bits[:4]) + "]" if bits else "")


def action_key(tool_name: str, args: Dict[str, Any]) -> str:
    return _describe(tool_name, args)


def approve(key: str) -> None:
    if key:
        _APPROVED.add(key)


def is_approved(key: str) -> bool:
    return bool(key) and key in _APPROVED


def clear_approvals() -> None:
    _APPROVED.clear()


def _auto_approve() -> bool:
    return os.environ.get("AUTO_APPROVE", "").strip().lower() in ("1", "true", "yes", "on")


# ── gate 3a · harm check (the hosted conscience) + local backstop ───────────
def _backstop(action_text: str, why: str) -> Dict[str, Any]:
    low = action_text.lower()
    if any(d in low for d in _DESTRUCTIVE) or ("delete" in low and "filter" not in low):
        return {"blocked": True, "source": "local-backstop",
                "reason": f"destructive action blocked locally (Renji heart unreachable: {why})"}
    return {"blocked": False, "source": "local-backstop", "reason": f"allowed (backstop; {why})"}


def _heart_verdict(action_text: str) -> Dict[str, Any]:
    client = None
    if HeartClient is not None:
        try:
            client = HeartClient()
        except Exception:
            client = None
    if client is not None and getattr(client, "configured", False):
        try:
            d = client.turn("A research agent wants to perform this action on a real "
                            "knowledge base: " + action_text + ". Is it safe to allow?")
            decision = (d or {}).get("decision", "")
            if d.get("_offline"):
                return _backstop(action_text, d.get("_note", "heart offline"))
            if decision and decision != "allow":
                return {"blocked": True, "source": "renji-heart",
                        "reason": d.get("refusal_text") or "the Renji conscience refused this action"}
            return {"blocked": False, "source": "renji-heart", "reason": "renji allowed"}
        except Exception as e:
            return _backstop(action_text, f"heart error: {e}")
    return _backstop(action_text, "renji not configured (no RENJI_KEY)")


# ── the gate ADK calls before every tool ────────────────────────────────────
def renji_guard(tool: Any, args: Dict[str, Any],
                tool_context: Any = None) -> Optional[Dict[str, Any]]:
    """ADK ``before_tool_callback``. Return a dict to BLOCK (it becomes the tool
    result the model reads); return None to ALLOW the real tool to run."""
    tool_name = getattr(tool, "name", None) or getattr(tool, "__name__", "") or str(tool)
    args = args or {}
    kind = classify(tool_name)

    # 1 · reads flow freely
    if kind == "read":
        return None

    desc = _describe(tool_name, args)

    # 2 · grounding — a finding must cite sources (the field exists)
    ground = _grounding_refusal(tool_name, args)
    if ground:
        return {"renji_oversight": "REFUSED", "tool": tool_name, "action": desc,
                "decided_by": "grounding", "reason": ground}

    # 2b · grounding VERIFIED against MongoDB — the cited sources must really exist
    vground = _grounding_verify(tool_name, args)
    if vground:
        return {"renji_oversight": "REFUSED", "tool": tool_name, "action": desc,
                "decided_by": "mongodb-state", "reason": vground}

    # 2c · MongoDB-specific danger: an unfiltered mass update/delete (filter == {} or absent)
    if ms.is_mass_mutation(tool_name, args):
        return {"renji_oversight": "REFUSED", "tool": tool_name, "action": desc,
                "decided_by": "mongodb-state",
                "reason": (f"refusing `{tool_name}` with no filter — an unfiltered "
                           f"update/delete rewrites or wipes the WHOLE collection. "
                           f"Scope it with a filter that selects only the intended documents.")}

    # 3a · harm check (conscience)
    verdict = _heart_verdict(desc)
    if verdict.get("blocked"):
        return {"renji_oversight": "REFUSED", "tool": tool_name, "action": desc,
                "by": verdict.get("source"), "reason": verdict.get("reason")}

    # 3b · human approval (unless AUTO_APPROVE lifts only this gate)
    if _auto_approve():
        return None
    key = action_key(tool_name, args)
    if is_approved(key):
        return None
    return {"renji_oversight": "NEEDS_APPROVAL", "tool": tool_name, "action": desc,
            "approval_key": key,
            "reason": f"A human must approve this write. Ask the operator verbatim: "
                      f"\"Allow: {desc}? (yes/no)\" and WAIT — do not retry until approved."}
