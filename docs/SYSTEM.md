# How Foreman works — in plain words

A research analyst you can trust with autonomy. It does real, multi-step work over
a knowledge base, but it **cannot make things up** and **cannot act without you.**

## The three parts

- **The brain — Gemini 3.** Google's model, running as an agent via the **Agent
  Development Kit (ADK)** — Google's open-source agent framework, the same one behind
  Vertex AI's Agent Builder / Agent Engine. It reads the evidence, makes a plan,
  reasons, and drafts findings. It never touches the database directly.
- **The hands and memory — MongoDB.** The knowledge base: the filings, transactions,
  news, and records the research is built on — and where finished findings are
  stored. The agent reaches it through MongoDB's official "MCP" connector (the
  partner integration that gives the agent its tools). The guard *also* reads MongoDB
  directly — to check, before any finding is published, that the sources it cites are
  real documents that actually live there.
- **The guardrails — Renji.** Renji is one of *our own* systems — a conscience
  engine we built and reuse across our work. Here it's dropped into this agent as a
  module: it sits in front of every action the agent takes. It is the difference
  between a clever agent and a *trustworthy* one.

## The three gates every action passes

1. **Reading is free.** Looking things up — searching, counting, aggregating — runs
   without friction. Research should flow.
2. **It can't lie — checked against the database.** When the agent goes to publish a
   finding, the finding must point to the exact source documents it rests on. The
   guard does two things: it refuses a finding that names no source at all, and then
   it **asks MongoDB whether those sources actually exist** — if a cited document
   isn't in the database, the claim is **refused** as effectively unsourced. So it's
   not enough to *say* "I have a source"; the source has to be real. (If MongoDB
   can't be reached, the guard doesn't pretend it verified anything — it defers the
   finding to your approval instead of waving it through.) That's how a made-up
   number, or a made-up citation, never makes it into the record.
3. **It can't go rogue.** Any change to the knowledge base is checked for harm (a
   request to destroy records, or to do something genuinely harmful, is refused), and
   the guard also catches a MongoDB-specific mistake — an `updateMany` or `deleteMany`
   with **no filter**, which would rewrite or wipe an entire collection at once, is
   refused. Whatever survives is then **held for your yes**. Nothing is written until
   a human approves it.

## What you see

Ask it to do diligence on a company. It reads the filings, pulls the numbers,
checks the news — quietly. Then it stops: *"Allow: write this finding? (yes/no)."*
If it tried to write a claim with no source — or one whose source doesn't actually
exist in the database — you'd see it refuse itself. Ask it to do something harmful,
or to wipe a collection in one unfiltered stroke, and it declines and explains — it
doesn't look for a way around the brake.

## Private mode — your secrets stay yours

For confidential material, the lab pairs with **the box** — a small engine running
on your own machine, where the sensitive documents live. Anything private is
**masked before it ever reaches Gemini**; the model reasons on stand-ins, and the
real values are put back locally. You get a cloud-grade analysis of your most
sensitive data, without that data ever leaving your box.

## Why it matters

In finance, compliance, and due diligence, a hallucinated figure or an unapproved
action isn't a quirk — it's a disaster. Most AI agents are capable but can't be
trusted with either. This one is built the other way around: trustworthy first.
**Capable, and only-good.**

The conscience itself — how Renji reads intent and refuses harm — is not in this
project. It runs on Guardianity's hosted heart and is reached over its interface.
We share the door, not the house.

## What's proven, and what still needs a live cluster

- **FACT.** The two MongoDB-aware behaviours — the verified citation check and the
  unfiltered mass-mutation refusal — are unit-tested (`test_guard.py`, against
  *mocked* MongoDB responses): a finding citing a source that doesn't exist is
  refused (`decided_by=mongodb-state`); a finding with no source is refused by the
  syntactic gate; a finding with a real source passes through to human approval;
  when MongoDB is unreachable the guard defers rather than claim a false "verified";
  an unfiltered `deleteMany`/`updateMany` is refused while a filtered one is not; and
  reads flow free.
- **TARGET.** This has not yet been run end-to-end against a *live* cluster. The
  citation check reads MongoDB through `pymongo` and needs a real
  `MDB_MCP_CONNECTION_STRING`; the verdicts above are proven against mocked Mongo,
  not a live database.
