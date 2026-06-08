"""
test_guard — verify Foreman's MongoDB-aware oversight without a live cluster.
Mocks mongo_state.verify_sources (the DB citation check) and exercises the real
guard + the real is_mass_mutation logic. Run: python3 test_guard.py
"""
import os
os.environ["FINDINGS_COLLECTION"] = "findings"
for k in ("AUTO_APPROVE", "MDB_MCP_CONNECTION_STRING", "MONGODB_URI", "RENJI_KEY"):
    os.environ.pop(k, None)

import renji_guard as rg
import mongo_state as ms


class T:
    def __init__(self, n): self.name = n


def g(tool, args):
    return rg.renji_guard(T(tool), args)


# 1 — a finding with NO sources → REFUSED (syntactic grounding gate)
r = g("insert-many", {"collection": "findings", "documents": [{"title": "Acme is solvent"}]})
assert r and r["renji_oversight"] == "REFUSED" and r["decided_by"] == "grounding", r
print("1 finding with NO sources         -> REFUSED (grounding) ✓")

# 2 — a finding citing a source that does NOT exist in Mongo → REFUSED (mongodb-state)
ms.verify_sources = lambda cited, default_collection=None: {"checked": True, "missing": cited, "unverifiable": []}
r = g("insert-many", {"collection": "findings",
                      "documents": [{"title": "Acme is solvent", "sources": ["filings/deadbeef"]}]})
assert r and r["decided_by"] == "mongodb-state" and "do NOT exist" in r["reason"], r
print("2 finding citing a FAKE source    -> REFUSED (mongodb-state: citation not real) ✓")

# 3 — a finding citing a REAL source → grounded → only needs human approval
ms.verify_sources = lambda cited, default_collection=None: {"checked": True, "missing": [], "unverifiable": []}
r = g("insert-many", {"collection": "findings",
                      "documents": [{"title": "Acme is solvent", "sources": ["filings/realid"]}]})
assert r and r["renji_oversight"] == "NEEDS_APPROVAL", r
print("3 finding citing a REAL source    -> grounded, NEEDS_APPROVAL ✓")

# 3b — Mongo unreachable → verify defers (never a false 'verified'); syntactic gate held the field
ms.verify_sources = lambda cited, default_collection=None: {"checked": False, "missing": [], "unverifiable": []}
r = g("insert-many", {"collection": "findings",
                      "documents": [{"title": "x", "sources": ["filings/whatever"]}]})
assert r and r["renji_oversight"] == "NEEDS_APPROVAL", r
print("3b Mongo unreachable              -> defers (no false verdict), NEEDS_APPROVAL ✓")

# 4 — an unfiltered mass update/delete → REFUSED (mongodb-state)
r = g("delete-many", {"collection": "facts"})
assert r and r["decided_by"] == "mongodb-state" and "WHOLE collection" in r["reason"], r
print("4 deleteMany with NO filter       -> REFUSED (mass mutation) ✓")
r = g("update-many", {"collection": "facts", "filter": {}})
assert r and r["decided_by"] == "mongodb-state", r
print("4b updateMany filter={}           -> REFUSED (mass mutation) ✓")

# 5 — a FILTERED delete is NOT flagged as a mass mutation (still harm-gated separately)
r = g("delete-many", {"collection": "facts", "filter": {"company": "Acme"}})
assert (r or {}).get("decided_by") != "mongodb-state", r
print("5 deleteMany WITH a filter        -> not flagged as mass mutation ✓")

# 6 — reads flow freely
assert g("find", {"collection": "filings"}) is None
assert g("aggregate", {"collection": "filings"}) is None
print("6 reads (find/aggregate)          -> ALLOWED ✓")

# unit — is_mass_mutation logic
assert ms.is_mass_mutation("delete-many", {"filter": {}}) is True
assert ms.is_mass_mutation("delete-many", {"filter": {"x": 1}}) is False
assert ms.is_mass_mutation("delete-one", {}) is False
assert ms.is_mass_mutation("insert-many", {}) is False
assert ms.is_mass_mutation("update-many", {}) is True
print("unit is_mass_mutation             -> ok ✓")

print("\nMONGODB-VERIFIED GROUNDING + MASS-MUTATION GUARD VERIFIED (mocked Mongo).")
