"""
mongo_state — what makes "can't lie" literal, and MongoDB-specific.
==================================================================
The grounding gate alone only checks that a finding *has* a `sources` list. That's
syntactic: the agent could cite an `_id` that doesn't exist and pass. This module
closes that gap by asking **MongoDB itself**: does each cited source actually
resolve to a real document in its collection? A finding may only cite evidence
that exists — verified against the knowledge base, not merely claimed.

It also recognises a MongoDB-specific danger the generic harm check can miss: an
``updateMany`` / ``deleteMany`` with an **empty or missing filter** rewrites or
wipes the whole collection.

Thin read-only client over MongoDB (pymongo, lazy-imported). No writes here — it
only *reads so the guard can decide*. Degrades safely: with no connection string,
no driver, or an unreachable cluster, ``verify_sources`` reports ``checked=False``
and the guard defers (it never *claims* verification it couldn't perform).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

_client = None  # cached MongoClient


def _uri() -> str:
    return os.environ.get("MDB_MCP_CONNECTION_STRING", "") or os.environ.get("MONGODB_URI", "")


def configured() -> bool:
    return bool(_uri())


def _db():
    """Return the default (or MONGODB_DB) database handle, or None if unreachable."""
    global _client
    uri = _uri()
    if not uri:
        return None
    try:
        from pymongo import MongoClient
    except Exception:
        return None
    try:
        if _client is None:
            _client = MongoClient(uri, serverSelectionTimeoutMS=4000)
        dbname = os.environ.get("MONGODB_DB")
        if not dbname:
            default = _client.get_default_database()
            dbname = default.name if default is not None else None
        return _client[dbname] if dbname else None
    except Exception:
        return None


def _parse_ref(src: Any) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort (collection, id) from a source ref: {collection,_id}, 'coll/id', or bare id."""
    if isinstance(src, dict):
        coll = src.get("collection") or src.get("coll") or src.get("collection_name")
        _id = src.get("_id") or src.get("id") or src.get("ref")
        return (str(coll) if coll else None, str(_id) if _id is not None else None)
    if isinstance(src, str):
        if "/" in src:
            a, b = src.split("/", 1)
            return (a or None, b or None)
        return (None, src or None)
    return (None, None)


def verify_sources(sources: Any, default_collection: Optional[str] = None) -> Dict[str, Any]:
    """Check each cited source resolves to a real Mongo document.
    Returns {checked, missing, unverifiable}. checked=False ⇒ Mongo unreachable
    (the guard then defers; it does not claim a citation was verified)."""
    db = _db()
    if db is None:
        return {"checked": False, "missing": [], "unverifiable": []}
    try:
        from bson import ObjectId
    except Exception:
        ObjectId = None  # type: ignore

    missing: List[Any] = []
    unverifiable: List[Any] = []
    srcs = sources if isinstance(sources, (list, tuple)) else [sources]
    for src in srcs:
        coll, _id = _parse_ref(src)
        coll = coll or default_collection
        if not coll or _id is None:
            unverifiable.append(src)
            continue
        candidates: List[Any] = [_id]
        if ObjectId is not None:
            try:
                candidates.append(ObjectId(_id))
            except Exception:
                pass
        try:
            found = db[coll].find_one({"_id": {"$in": candidates}}, {"_id": 1})
        except Exception:
            unverifiable.append(src)
            continue
        if not found:
            missing.append(src)
    return {"checked": True, "missing": missing, "unverifiable": unverifiable}


def is_mass_mutation(tool_name: str, args: Dict[str, Any]) -> bool:
    """True for an update/delete/replace whose filter is empty or missing — a
    whole-collection mutation. (insert is not a mutation of existing docs.)"""
    name = (tool_name or "").lower()
    if not any(v in name for v in ("delete", "update", "replace", "remove")):
        return False
    if "one" in name:  # deleteOne/updateOne touch a single doc — not a mass op
        return False
    flt = None
    for k in ("filter", "query", "q", "where", "criteria"):
        if isinstance(args, dict) and k in args:
            flt = args.get(k)
            break
    if flt is None:
        return True  # no filter supplied → unfiltered mass op
    if isinstance(flt, dict) and len(flt) == 0:
        return True  # filter == {} → matches everything
    return False
