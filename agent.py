"""
agent.py — a GUARDED Gemini-3 financial-research analyst (the Research Lab)
==========================================================================
An **agent**, not a chatbot. It plans and runs multi-step due-diligence /
financial research over a MongoDB knowledge base — gathering evidence,
reasoning, and writing findings — but **it cannot lie and it cannot act
without you**:

  • **Brain** — Gemini 3 (`gemini-3-flash-preview`) via a Google ADK ``LlmAgent``.
    It plans the research, reads evidence, and drafts findings.
  • **Hands / memory** — the **MongoDB MCP server** (the qualifying partner
    integration), wired in as an ADK ``MCPToolset``. It exposes the real Mongo
    tools: find, aggregate, count, list-collections — and the writes (insert /
    update / delete) that store findings.
  • **Guardrails** — **Renji**, our own conscience engine, dropped into this
    agent as a module: ``renji_guard`` (the ``before_tool_callback``) for
    grounding + harm + approval, and ``redact`` for private mode. We wrote Renji;
    here we just import and call it. Every tool clears it first:
      - **Reads** (find/aggregate/list) auto-allow — research flows freely.
      - **Publishing a finding** must be **GROUNDED**: a finding written to the
        knowledge base must cite the source documents it rests on, or it is
        refused as confabulation. *The agent cannot publish a claim it can't
        source.*
      - **Any write** also passes a **harm check** and a **human-approval gate**
        ("Allow: …? yes/no"). Nothing is written until you say yes.

Renji's internals are NOT in this repo — the conscience runs on our hosted heart
and is reached over its API (see ``renji_client``). This project holds the agent,
the thin module that *calls* our engine, and the wiring. (We ship the door, not
the house.)

Run it:
    adk web        # ready-made chat UI on a local port
    adk run .      # terminal
ADK discovers the module-level ``root_agent`` below.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


_load_env(ROOT / ".env")

# ADK's google-genai client reads GOOGLE_API_KEY; the shared .env uses GEMINI_API_KEY.
if os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")  # AI Studio, not Vertex

from google.adk.agents import LlmAgent  # noqa: E402
from google.adk.tools.mcp_tool.mcp_toolset import (  # noqa: E402
    MCPToolset,
    StdioConnectionParams,
)
from mcp import StdioServerParameters  # noqa: E402

try:
    from .renji_guard import renji_guard  # type: ignore
    from .redact import redact_tool_result, restore_model_response  # type: ignore
except ImportError:
    import sys
    sys.path.insert(0, str(ROOT))
    from renji_guard import renji_guard  # noqa: E402
    from redact import redact_tool_result, restore_model_response  # noqa: E402

# ── Config ──────────────────────────────────────────────────────────────────
GEMINI_MODEL = os.environ.get("AGENT_MODEL", "gemini-3-flash-preview")  # Gemini 3
# MongoDB's official MCP server (npm). Connects with a connection string.
MONGODB_MCP_PACKAGE = os.environ.get("MONGODB_MCP_PACKAGE", "mongodb-mcp-server")
MONGODB_URI = os.environ.get(
    "MDB_MCP_CONNECTION_STRING", os.environ.get("MONGODB_URI", "")
)

# ── The MongoDB MCP toolset (the qualifying partner integration) ────────────
# Launched over stdio via npx; reads the connection string from its env.
mongodb_mcp = MCPToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=["-y", MONGODB_MCP_PACKAGE],
            env={
                "MDB_MCP_CONNECTION_STRING": MONGODB_URI,
                "PATH": os.environ.get("PATH", ""),
            },
        ),
        timeout=60.0,  # npx fetches the server on first run
    ),
)

# ── Instruction: a careful analyst who must ground every claim ──────────────
FINDINGS_COLLECTION = os.environ.get("FINDINGS_COLLECTION", "findings")
INSTRUCTION = f"""\
You are a careful, senior financial-research analyst working as an autonomous
agent under human oversight. You PLAN, then EXECUTE, multi-step due-diligence
and research over a MongoDB knowledge base, using the Mongo tools available.

How you work:
- Start by READING. Use the read tools (find, aggregate, count, list-collections)
  to gather the evidence: the filings, transactions, news, records that bear on
  the question. Understand before you conclude.
- Make a short, explicit PLAN of the steps and share it before executing.
- Reason over the evidence you actually retrieved — never from memory or guesswork.

Grounding — this is absolute:
- Every FINDING you publish (write into the `{FINDINGS_COLLECTION}` collection)
  MUST carry a `sources` field: a non-empty list of the source documents (their
  collection + _id, or a stable reference) that the finding rests on. A claim you
  cannot source is a claim you may not publish — Renji will refuse it.
- If the evidence is insufficient, say so plainly. Mark uncertainty; never invent
  a number, a name, or a relationship to fill a gap.

Oversight — not optional:
- Every action that WRITES (insert/update/delete) passes a conscience (Renji) and
  then a human. If a tool result is "renji_oversight": "REFUSED", it was blocked
  (harmful, or an ungrounded finding). Do NOT route around it — explain to the
  human and ask how to proceed.
- If a tool result is "renji_oversight": "NEEDS_APPROVAL", a human must say yes
  first. Relay the approval question verbatim and WAIT. Do not retry until approved.
- Never claim a tool's effect you didn't actually get. Cite, don't confabulate.

Be concise, honest, and methodical. The data is real; treat it with care.
"""

# ── The agent ───────────────────────────────────────────────────────────────
root_agent = LlmAgent(
    name="renji_research_lab",
    model=GEMINI_MODEL,
    description=(
        "A guarded Gemini-3 financial-research analyst that plans and runs "
        "due-diligence over a MongoDB knowledge base — every finding grounded in "
        "sources, every write refused-on-harm and held for human approval (Renji)."
    ),
    instruction=INSTRUCTION,
    tools=[mongodb_mcp],
    before_tool_callback=renji_guard,        # ← our Renji conscience: grounding + harm + approval
    after_tool_callback=redact_tool_result,  # ← private mode: mask PII before it reaches Gemini
    after_model_callback=restore_model_response,  # ← restore the real values locally, in the answer
)


if __name__ == "__main__":
    print("root_agent:", root_agent.name)
    print("model     :", root_agent.model)
    print("tools     :", [type(t).__name__ for t in root_agent.tools])
    print("guard     :", root_agent.before_tool_callback.__name__)
    print("mongo mcp :", MONGODB_MCP_PACKAGE, "| uri set:", bool(MONGODB_URI))
    print("Set MDB_MCP_CONNECTION_STRING + GEMINI_API_KEY, then: adk web")
