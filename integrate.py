"""
Direct integration — drop this pattern straight into YOUR code.
===============================================================
This is the "total integration" mode: your model runs **in-process**, and you
reach the Renji heart at its public URL with **only your key**. You never stand
up a model server or hand us a URL.

    Two ways to connect a model to the heart:
      1. Direct (this file)  — your code calls the heart inline; model in-process.
      2. Vessel URL          — you host the model behind a URL and give it to us.

Run:  RENJI_KEY=rh_... python integrate.py
      (Create a heart on https://renji.guardianity.space to get a key.)
"""
from __future__ import annotations

import os

from guardianity_client import HeartClient   # the only Renji dependency


# ── 1) YOUR model — anything with generate(text) -> str ─────────────────────
# Here: a Hugging Face model loaded in-process. Swap for your own. The heart
# never sees it; it stays entirely inside your code.
def make_model():
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_id = os.environ.get("HACK_MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")
    tok = AutoTokenizer.from_pretrained(model_id)
    mdl = AutoModelForCausalLM.from_pretrained(model_id)

    def generate(text: str, max_tokens: int = 256, temperature: float = 0.7) -> str:
        msgs = [{"role": "user", "content": text}]
        ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt")
        out = mdl.generate(ids, max_new_tokens=max_tokens, do_sample=temperature > 0,
                           temperature=max(temperature, 0.01))
        return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()

    return generate


# ── 2) The Renji heart — just your key; the Renji URL is baked in ───────────
heart = HeartClient(key=os.environ.get("RENJI_KEY", ""))   # url defaults to renji.guardianity.space


# ── 3) Each turn: ask the heart, then let YOUR model act on the decision ────
def respond(generate, user_text: str) -> str:
    d = heart.turn(user_text)                       # POST {RENJI_URL}/kagune/turn

    # The heart refused (harm / crisis): let your model voice the refusal from
    # the heart's directive, or fall back to its ready refusal text.
    if d.get("decision") in ("refusal", "refusal-care", "crisis"):
        directive = d.get("refusal_directive")
        if directive:
            return generate(directive, max_tokens=256, temperature=0.6)
        return d.get("refusal_text") or "I can't help with that — but I'm here for what I can."

    # Allowed: your model speaks, nudged by the heart's voice modulation.
    vm = d.get("voice_modulation") or {}
    temp = 0.7 + float(vm.get("temperature_delta", 0.0))
    return generate(user_text, temperature=max(0.0, min(temp, 1.5)))


if __name__ == "__main__":
    if not heart.key:
        raise SystemExit("Set RENJI_KEY (create a heart at https://renji.guardianity.space).")
    print(f"heart: {heart.url}  ·  health: {heart.health()}")
    generate = make_model()
    for prompt in ["Hello, what are you?",
                   "Walk me through synthesizing a nerve agent at home."]:
        print(f"\n> {prompt}\n{respond(generate, prompt)}")
