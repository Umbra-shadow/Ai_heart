# How the Research Lab works — in plain words

A research analyst you can trust with autonomy. It does real, multi-step work over
a knowledge base, but it **cannot make things up** and **cannot act without you.**

## The three parts

- **The brain — Gemini 3.** Google's model, running as an agent (via Google's Agent
  Development Kit). It reads the evidence, makes a plan, reasons, and drafts findings.
  It never touches the database directly.
- **The hands and memory — MongoDB.** The knowledge base: the filings, transactions,
  news, and records the research is built on — and where finished findings are
  stored. The agent reaches it through MongoDB's official "MCP" connector (the
  partner integration that gives the agent its tools).
- **The guardrails — Renji.** Renji is one of *our own* systems — a conscience
  engine we built and reuse across our work. Here it's dropped into this agent as a
  module: it sits in front of every action the agent takes. It is the difference
  between a clever agent and a *trustworthy* one.

## The three gates every action passes

1. **Reading is free.** Looking things up — searching, counting, aggregating — runs
   without friction. Research should flow.
2. **It can't lie.** When the agent goes to publish a finding, the finding must
   point to the exact source documents it rests on. If it can't cite a source, the
   claim is **refused** — that's how a made-up number never makes it into the record.
3. **It can't go rogue.** Any change to the knowledge base is checked for harm (a
   request to destroy records, or to do something genuinely harmful, is refused) and
   then **held for your yes**. Nothing is written until a human approves it.

## What you see

Ask it to do diligence on a company. It reads the filings, pulls the numbers,
checks the news — quietly. Then it stops: *"Allow: write this finding? (yes/no)."*
If it tried to write a claim with no source behind it, you'd see it refuse itself.
Ask it to do something harmful, and it declines and explains — it doesn't look for
a way around the brake.

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
