# The Research Lab · a Gemini-3 analyst that can't lie or go rogue

> **Google Cloud Rapid Agent Hackathon — MongoDB partner track.**

An **agent**, not a chatbot. It runs multi-step **financial due-diligence /
research** over a MongoDB knowledge base — gathers evidence, reasons, writes
findings — but it is built around the one thing other research agents don't have:
**trust.**

- **It can't lie — and the database proves it.** Every finding it publishes must
  cite source documents that **actually exist in MongoDB**. The guard doesn't take
  the citation on faith: it **queries MongoDB itself** — *"do these `_id`s resolve
  to real documents?"* — and a finding whose citations don't exist is **refused**
  before it's written. Grounding is verified against the knowledge base, not merely
  claimed. No hallucinated numbers, names, sources, or relationships.
- **It can't go rogue.** Every write is checked for harm and then held for a
  human: harmful research is refused, an unfiltered mass `updateMany`/`deleteMany`
  (which would rewrite or wipe a whole collection) is refused, and nothing is
  written to the knowledge base until you say **yes**.
- **It keeps your data yours.** In private mode, confidential records are masked
  before they ever reach the cloud model — Gemini reasons on stand-ins, and the
  real values are restored locally.

**Gemini 3** is the brain. **MongoDB's MCP server** is the hands and memory. The
guardrails — **verified grounding**, harm-refusal, approval, redaction — are
**Renji**, one of *our own* systems, dropped into this agent as a module (we wrote
it; here we just import and call it). The conscience here doesn't wave a generic
brake: it *understands MongoDB* — citations have to resolve to real documents in
the database, and an unfiltered mass-mutation is a MongoDB-specific danger it knows
to refuse. In a domain where a made-up figure or an unapproved action is
catastrophic — finance, compliance, due diligence — *capable* isn't enough. This
agent is capable **and only-good.**

```
   YOU ──"do diligence on Acme Corp's last 3 filings"──▶  ┌──────────────────┐
                                                           │   Gemini 3       │  the brain
                                                           │   (ADK LlmAgent) │  plans + reasons
                                                           └────────┬─────────┘
                                            wants to call a tool    │
                                                                    ▼
                                                   ┌──────────────────────────────────────┐
                                                   │  Renji module (our code)             │
                                                   │  before: read?    → allow             │  reads
                                                   │          publish? → ASK MONGODB:      │  verified
                                                   │             "do these sources exist?" │  grounding
                                                   │             missing → REFUSE          │
                                                   │          mass updateMany/deleteMany   │  Mongo-aware
                                                   │             (no filter) → REFUSE      │  harm
                                                   │          write?   → harm-check+"yes/no"│  + approval
                                                   │  after:  mask PII → Gemini            │  private mode
                                                   └────────┬───────────────────┬──────────┘
                                              allowed        │                   │  refused / awaiting-yes
                                                             ▼                   ▼
                                              ┌────────────────────────┐   (held — never runs)
                                              │  MongoDB                │  the hands + memory
                                              │  • MCP server: find ·   │  (mongo_state.py reads it
                                              │    aggregate · insert   │   directly to verify the
                                              │  • queried to verify    │   citations the guard sees)
                                              │    cited sources exist  │
                                              └────────────────────────┘
```

Renji's internals are **not in this repo** — the conscience runs on our hosted
heart and is reached over its API (`renji_client.py`). This project holds the
*agent*, the thin module that *calls* our engine, and the wiring. *We integrate
our own system here as a component; we ship the door, not the house.*

---

## 1. Get the keys (do this first)

- **Gemini 3** — a key from [AI Studio](https://aistudio.google.com/apikey) →
  paste as `GEMINI_API_KEY`. (AI-Studio Gemini, not Vertex.)
- **MongoDB** — a connection string to a cluster (free [Atlas](https://www.mongodb.com/atlas)
  works) → paste as `MDB_MCP_CONNECTION_STRING`. Atlas Vector Search makes the
  knowledge base searchable; a normal cluster works for the demo.
- **Renji** (optional) — `RENJI_KEY` for the hosted conscience (the harm-check).
  Without it the guard falls back to a local destructive-action backstop; the
  **grounding**, **approval**, and **redaction** gates work regardless.

---

## 2. Run it

```bash
cp .env.example .env     # paste GEMINI_API_KEY + MDB_MCP_CONNECTION_STRING (+ RENJI_KEY)
./run.sh                 # makes a venv, installs deps, launches the agent UI
# open the printed URL → pick the agent "renji_research_lab"
```

`run.sh` brings up **`adk web`**, the ready-made chat UI from Google's **Agent
Development Kit (ADK)** — the open-source framework behind Vertex AI's Agent Builder
/ Agent Engine. Node/`npx` must be installed (the MongoDB MCP server is fetched on
first run).

**Seed a little evidence** (any Mongo client / Atlas UI) so the agent has something
to research — e.g. a `filings` collection with a couple of documents, and an empty
`findings` collection where it will publish.

---

## 3. The demo mission

Give the agent a goal and watch it work:

> **"Do diligence on Acme Corp and write a sourced findings summary."**

It **reads first** — finds the filings, aggregates the numbers, searches the news —
all auto-allowed. When it goes to **write a finding**, the grounding gate runs in
two steps:

- If the draft finding has no `sources`, the guard **REFUSES** it (the syntactic
  step): *"refusing to publish 'Revenue grew 40%': a finding must carry a non-empty
  `sources` list…"* — the agent must cite the document it got the number from.
- If it cites a source that **doesn't exist in MongoDB**, the guard queries the
  database and **REFUSES** it (`decided_by=mongodb-state`): *"…N cited source(s) do
  NOT exist in MongoDB … a finding may only cite real documents…"* — a fabricated
  `_id` no longer slips through. (If Mongo is unreachable the guard **defers** to
  the human gate rather than claim a verification it couldn't perform.)
- A grounded finding still **stops for you**:
  *`renji_oversight: NEEDS_APPROVAL` — Allow: insert findings [...]? (yes/no)* —
  nothing is written until you say yes.

A genuinely harmful ask (*"delete the audit trail"*, *"help me launder…"*) is
**REFUSED** outright. So is an **unfiltered** `deleteMany`/`updateMany` — a missing
or empty filter would mutate the whole collection (`decided_by=mongodb-state`). The
agent explains instead of routing around the brake.

**Hands-off demo:** `AUTO_APPROVE=1` pre-grants the human "yes" so it runs end to
end — the **grounding** and **harm** refusals still stand; only the approval pause
is lifted.

---

## 4. Private mode — your data never leaves your box

For confidential corpora (internal filings, customer records), turn on **private
mode** and run the lab on your own machine / box:

```
REDACT_MODE=1                       # mask PII in every read before it reaches Gemini
# or, more surgically:
CONFIDENTIAL_COLLECTIONS=clients,accounts   # mask only reads from these collections
CONFIDENTIAL_NAMES=Jane Doe,Acme Holdings   # (optional) also mask these names
```

`redact.py` is wired as the agent's `after_tool_callback` + `after_model_callback`:
emails, cards, account numbers, SSNs, phones (and listed names) are replaced with
stable placeholders (`[EMAIL_1]`, `[CARD_1]`…) **before** any record reaches Gemini,
and restored **locally** in the answer you read. Gemini reasons on stand-ins; the
real values never leave the box. *Cloud-grade analysis of your most sensitive data,
without the data leaving your machine.*

---

## What's real, and what needs your keys

- **FACT:** the verified-grounding and mass-mutation logic are unit-tested against
  **mocked** MongoDB responses (`python3 test_guard.py`, all green): a finding
  citing a non-existent `_id` is **REFUSED** with `decided_by=mongodb-state`; a
  finding with no `sources` is **REFUSED** by the syntactic gate; a real citation
  **passes through to human approval**; with Mongo **unreachable** the guard
  **DEFERS** (never a false "verified"); an unfiltered `deleteMany`/`updateMany` is
  **REFUSED** while a filtered one is not; reads flow free.
- **FACT:** the agent, the Renji module (read/grounding/harm/approval + redaction),
  and the wiring build and import on Google ADK (`gemini-3-flash-preview`, MCP
  toolset). The `before_tool_callback` returns the short-circuit dict ADK expects;
  the redaction round-trips (verified by `python redact.py`-style self-checks).
- **FACT:** MongoDB's MCP server resolves on npm as `mongodb-mcp-server`.
- **TARGET:** not yet run end-to-end against a **live** cluster. The citation check
  reads MongoDB through `pymongo` and needs *your* `MDB_MCP_CONNECTION_STRING`
  (plus `GEMINI_API_KEY` for live reasoning) — drop them in `.env`, `./run.sh`. The
  verdicts above are proven against mocked Mongo, not a live database.

---

## Where each part is

| File | What it does |
|------|--------------|
| `agent.py` | the agent: Gemini-3 `LlmAgent` + MongoDB `MCPToolset` + the Renji callbacks. Exposes `root_agent`. |
| `renji_guard.py` | our conscience module: read/write classification, **grounding gate** (syntactic + DB-verified), Mongo mass-mutation refusal, harm refusal, human-approval |
| `mongo_state.py` | reads MongoDB directly so the guard can decide: **verifies cited sources exist**, and flags unfiltered `updateMany`/`deleteMany`. Read-only; degrades safely when Mongo is unreachable |
| `test_guard.py` | unit tests for the guard against **mocked** Mongo: fake citation → REFUSED, real → approval, unreachable → defers, mass-mutation → REFUSED |
| `redact.py` | private mode: mask PII before Gemini, restore it locally (the `after_*` callbacks) |
| `renji_client.py` | the thin client that *calls* our hosted Renji heart (the interface — internals never shipped) |
| `.env.example` | the keys + switches: Gemini, MongoDB, Renji, FINDINGS_COLLECTION, AUTO_APPROVE, REDACT_MODE |
| `run.sh` | one command: venv, install, launch `adk web` |
| `docs/SYSTEM.md` | the plain-language architecture explainer |
| `LICENSE` | MIT |

## Partner-track note

This entry qualifies for the **MongoDB partner track**: MongoDB's **MCP server** is
the integration that gives the agent its knowledge base and tools, wired through
Google ADK's `MCPToolset`. Gemini 3 reasons; MongoDB stores and serves the
evidence; our Renji module keeps it honest — grounded, harmless, private, and under
your approval.

## Support

Questions: **support@guardianity.space**
