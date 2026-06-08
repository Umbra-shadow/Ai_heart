"""
live_check — prove the MongoDB-verified grounding against the REAL cluster.
Seeds one real source doc, then shows: a finding citing it is grounded, a finding
citing a fabricated _id is REFUSED (decided_by=mongodb-state). Cleans up after.
Run inside the venv:  python live_check.py
"""
import os
from pathlib import Path

# load .env (MDB_MCP_CONNECTION_STRING / MONGODB_URI, etc.)
env = Path(__file__).resolve().parent / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# use a dedicated throwaway DB so we never touch real data
os.environ.setdefault("MONGODB_DB", "renji_grounding_test")
os.environ.pop("AUTO_APPROVE", None)

import mongo_state as ms
import renji_guard as rg


class T:
    def __init__(self, n): self.name = n


print("configured (URI present):", ms.configured())
db = ms._db()
print("cluster reachable:", db is not None, "| db:", db.name if db is not None else None)
if db is None:
    raise SystemExit("Could not reach the cluster — check the URI / Atlas IP allowlist.")

coll = db["filings"]
real_id = coll.insert_one({"title": "Acme Corp 10-K (2025)", "revenue_usd": 1_200_000_000}).inserted_id
print(f"seeded a REAL source: filings/_id={real_id}")

fake_id = "0123456789abcdef01234567"  # a well-formed ObjectId that does not exist

print("\n-- mongo_state.verify_sources (live) --")
print("  real:", ms.verify_sources([{"collection": "filings", "_id": str(real_id)}]))
print("  fake:", ms.verify_sources([{"collection": "filings", "_id": fake_id}]))

print("\n-- renji_guard on a published finding (live) --")
real = rg.renji_guard(T("insert-many"), {"collection": "findings",
        "documents": [{"title": "Acme is solvent", "sources": [{"collection": "filings", "_id": str(real_id)}]}]})
fake = rg.renji_guard(T("insert-many"), {"collection": "findings",
        "documents": [{"title": "Acme is solvent", "sources": [{"collection": "filings", "_id": fake_id}]}]})
print(f"  cites REAL source -> {real.get('renji_oversight') if real else 'ALLOWED'} "
      f"({(real or {}).get('decided_by','-')})")
print(f"  cites FAKE source -> {fake.get('renji_oversight')} ({fake.get('decided_by')})")
print(f"     reason: {fake.get('reason','')[:90]}")

# cleanup
coll.delete_one({"_id": real_id})
print("\ncleaned up the seeded doc.")
ok = (real and real.get("renji_oversight") == "NEEDS_APPROVAL"
      and fake and fake.get("decided_by") == "mongodb-state")
print("LIVE GROUNDING VERIFIED ✓" if ok else "UNEXPECTED RESULT ✗")
