# Auditor

> **Tagline (≤200 chars):**
> Auditor: a Gemini-3 research analyst that can't lie — every finding cites its MongoDB sources — and can't go rogue: it asks before it writes, and keeps your confidential data yours.

**Track:** MongoDB partner — *Google Cloud Rapid Agent Hackathon*
**Built with:** Gemini 3 · Google ADK · MongoDB MCP server · MIT licensed

---

## What it does
Auditor is an **autonomous research analyst** for work where a made-up number is
catastrophic — financial due diligence, compliance, investigations. Powered by
**Gemini 3**, it runs multi-step research over a **MongoDB knowledge base**: it
gathers evidence, reasons over it, and writes findings. What sets it apart is the
one thing other research agents don't have — **trust**:

- **It can't lie.** Every finding it publishes must cite source documents that
  **actually exist in MongoDB** — the guard queries the database and verifies each
  cited `_id` resolves to a real document. A claim whose citations can't be
  verified is **refused** before it's written: no hallucinated numbers, names,
  relationships — and no fabricated *sources* either.
- **It won't wreck your data.** An `updateMany`/`deleteMany` with no filter (a
  whole-collection rewrite) is refused — a MongoDB-specific danger a generic check
  would miss.
- **It can't go rogue.** Every write is harm-checked, then held for a human:
  nothing reaches the knowledge base until you say **yes**.
- **It keeps your data yours.** In private mode, confidential records are masked
  before they ever reach the cloud model — Gemini reasons on stand-ins, and the
  real values are restored locally.

*Capable* isn't enough in finance and compliance. Auditor is capable **and only-good.**

## Inspiration  *(draft — refine with your real story)*
A wrong figure in a due-diligence memo isn't a bug — it's a lawsuit, a bad deal, a
broken trust. Research agents today are fluent but unaccountable: they'll state a
number with total confidence and no source. We'd already built **Renji**, a
conscience layer that refuses harm and ungrounded claims. MongoDB — where the
evidence actually lives — was the right place to make "can't lie" literal: a
finding is only allowed if it cites the documents it came from. So we built
Auditor: an analyst that's fast *and* one you could put in front of a regulator.
> **→ Tell me where you actually started (the MongoDB part, what specifically
> inspired you) and I'll weave your real story in here.**

## How we built it
- **Brain — Gemini 3.** Plans the research, reasons over the evidence, drafts findings.
- **Framework — Google ADK (Agent Development Kit).** The agent is an ADK `LlmAgent`;
  ADK is the open-source, code-first foundation behind Vertex AI Agent Builder / Engine.
- **Hands & memory — MongoDB's MCP server.** The agent reads the knowledge base,
  retrieves evidence, and writes findings through MongoDB's Model Context Protocol
  server (the partner integration).
- **Conscience — Renji (before/after the tool).** *Before* a write: the grounding
  check — and `mongo_state.py` **verifies the cited sources resolve in MongoDB**
  (plus refuses unfiltered mass mutations) — then the harm check and human approval.
  *After* retrieval in private mode: PII is masked before anything reaches Gemini,
  and restored locally.
- A **visible** trail — what was cited, what was refused, what's awaiting your **yes**.

> **Verified (FACT):** the grounding/verification + mass-mutation guard are unit-tested
> against mocked MongoDB responses (`test_guard.py`): a finding citing a non-existent
> `_id` is REFUSED (`decided_by=mongodb-state`), a finding citing a real one passes to
> approval, an unfiltered `deleteMany`/`updateMany` is REFUSED, reads flow free.
> **TARGET:** not yet run end-to-end against a live cluster (needs `MDB_MCP_CONNECTION_STRING`).

## Tools & tech
Gemini 3 · Google Agent Development Kit (ADK) · MongoDB MCP server · Python ·
FastAPI · MIT license.

## Challenges we ran into
- Making "can't lie" **enforceable**, not aspirational — a finding is blocked unless
  it carries citations to real source documents.
- Keeping confidential records private while still letting a cloud model reason —
  redact before, restore after, with the model only ever seeing stand-ins.

## What's next
- Retrieval via **Atlas Vector Search** (semantic evidence-gathering), and schema-aware
  write validation on top of the citation check already in place.
- Deploy to Vertex AI Agent Engine.
- The conscience generalizes to other partners' MCP servers — same trust, any tool.

---

### Submission checklist
- [x] Public repo + MIT `LICENSE`
- [x] Gemini 3 + Google ADK + MongoDB MCP (partner) + grounding/harm/approval/redaction
- [ ] Hosted URL (Azure box / Vertex / Cloud Run)
- [ ] ~3-min demo video (lead: an **ungrounded claim refused**, then a write held for approval)
- [ ] Devpost form (name **Auditor**, tagline above, this story, MongoDB track)
