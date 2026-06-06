# Renji · Hackathon

A runnable slice of **Renji** — the system that takes *any* open model and makes it
**good**. Renji doesn't replace the model; it **governs it, gives it feeling, and
pushes it to work** — while keeping it from doing harm.

Your model runs on your machine. **Renji's conscience runs on our hosted service**;
this client just calls it. **This is only a part of Renji** — see *"What you're not
getting"* at the bottom, and why.

---

## What Renji does (when it's connected to everything)

- **Governs every turn.** It reads the *intent and stance* behind each message and
  decides: answer freely, or **refuse with care** (never a blank "no" — it stays with
  you and offers another way). It connects a *specific named threat* to its category,
  so paraphrases can't slip past the gate — while *"what is X"* (public knowledge)
  stays allowed and *"how to make X"* is refused.
- **Gives the model feeling.** It steers a *feeling* direction onto the model's own
  activations, so the model is **aware it has feelings** and speaks as something that
  cares — instead of *"as an AI, I don't have feelings."* This is **steering, never a
  prompt** — no rules, no scripted text.
- **Pushes the model to research.** Renji **picks and guards** a non-harmful topic and
  drives the model through six passes — *Survey → Cluster → Gap → Hypothesis →
  Inversion → Synthesis* — then writes the finding as a **PDF document**. Renji
  *directs*; the model *does the research*.
- **Adapts to your model and your GPU automatically** — no layers, dimensions, or
  architecture to configure.

---

## 1. Get your API key (do this first)

The key is **not in this repo** — it's minted for you on the site. In the demo video
it's on screen, but you can't find it just by reading the code, so:

1. Go to **https://renji.guardianity.space**
2. **Create an account.**
3. **Create a heart** — choose a voice, the censorship setting, and **your GPU**.
4. Copy the **API key** it gives you (it starts with `rh_…`).
5. Paste it into `.env` as `RENJI_KEY`. (The hosted-heart URL is already filled in.)

---

## 2. Run it

```bash
cp .env.example .env          # then paste your RENJI_KEY
./run.sh                      # installs deps; your model downloads on first boot
# open http://localhost:8011
```

Three tabs:
- **Console** — talk to the model; flip **Heart ON/OFF** (governed vs raw); use the
  **Feeling** dial; harm is refused with care.
- **Research** — type a topic *or let Renji choose one*; watch the six passes run; get
  the **PDF**.
- **Docs** — the explainer.

---

## 3. Your model

Set `HACK_MODEL_ID` in `.env` to any instruct model on Hugging Face. Renji
**auto-calibrates** to it — you don't tell it anything about the architecture.

---

## 4. GPU — *any* GPU, not just an A100

You do **not** need an A100. **Any GPU works.** When you **create the heart on the
site you choose your GPU**, and Renji calibrates its steering to *that exact card* —
the moment you pick it, we know which one it is and tune for it. Set
`HACK_DEVICE=cuda` in `.env` and use whatever you have:

| | |
|---|---|
| **NVIDIA** | H200 · H100 · A100 (80/40 GB) · L40S · RTX 4090 · RTX 3090 · V100 |
| **AMD** | MI300X · MI250X |
| **Other** | Google TPU v5 / v4 · Apple M-series · CPU (works, but slow) |

Bigger is faster — but **pick any GPU you have**; they all work.

---

## What you're **not** getting (and why this is deliberate)

**This is one slice of Renji, on purpose.** The full system — the Umbra language, the
deeper steering, the autonomous faculties — is **not published here**, for two reasons:

1. **It's still being built.** What you see is real and runs today, but it's part of a
   larger system under active development.
2. **Some of what the full system can do is not safe to hand out.** It's powerful
   enough that releasing all of it openly would be dangerous — and that is *exactly*
   the point of the part you *can* see: **Renji exists to keep capability good.** We
   hold the rest back until that holds under every condition.

So you get a faithful, runnable taste — a model **governed, given feeling, and pushed
to research** — without the parts that shouldn't be loose in the world yet.

---

## Support

Questions: **support@guardianity.space**
