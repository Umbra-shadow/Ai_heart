"""
llm — the LOCAL model (the "vessel"). YOUR model, your priority.
================================================================
This is the only heavy thing the demo runs on your machine; the conscience is
remote (guardianity_client → our hosted heart). A thin `transformers` wrapper:
load a model from Hugging Face and generate.

It ADAPTS to whatever vessel you bring — it never asks you to change models. The
approach mirrors the V10/V11 colab vessel loader:
  * one model class for everything: AutoModelForCausalLM (works for Gemma/Qwen/
    Llama/Mistral incl. Gemma 3n "E4B"),
  * a DYNAMIC prompt format: try the model's chat template with TYPED content
    first ([{"type":"text",...}] — what multimodal templates like Gemma 3n need),
    fall back to plain-string content (standard instruct models), then raw text —
    rejecting a result where the template rendered the list literally.
Auto dtype (bfloat16 on CUDA), proper turn-end stop tokens, gentle repetition
control. CPU or CUDA.
"""
from __future__ import annotations

import os


class LocalLLM:
    def __init__(self, model_id: str, device: str = "cpu", dtype: str = "auto"):
        self.model_id = model_id
        self.device = device
        self.dtype = dtype
        self.model = None
        self.tok = None
        self.feeling = None       # white-box feeling steering (set at boot)
        self.ready = False
        self.err = ""

    def boot(self) -> None:
        """Download (first run) + load the model. Sets .ready, or .err on failure."""
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            dt_map = {"float16": torch.float16, "bfloat16": torch.bfloat16,
                      "float32": torch.float32}
            torch_dtype = dt_map.get(self.dtype)
            if torch_dtype is None:                      # "auto" → fast + stable
                _cuda = (self.device == "cuda" and torch.cuda.is_available())
                torch_dtype = torch.bfloat16 if _cuda else torch.float32
            token = os.environ.get("HF_TOKEN") or None   # gated models (e.g. Gemma)

            self.tok = AutoTokenizer.from_pretrained(self.model_id, token=token)
            # Some abliterated re-uploads ship WITHOUT a chat template; without one
            # the model just continues your text (the echo loop). Supply Gemma's.
            if not getattr(self.tok, "chat_template", None) and "gemma" in self.model_id.lower():
                self.tok.chat_template = (
                    "{{ bos_token }}{% for message in messages %}"
                    "{{ '<start_of_turn>' + (message['role'] if message['role'] != 'assistant' "
                    "else 'model') + '\n' + message['content'] | trim + '<end_of_turn>\n' }}"
                    "{% endfor %}{% if add_generation_prompt %}{{ '<start_of_turn>model\n' }}{% endif %}"
                )

            kw = dict(token=token, low_cpu_mem_usage=True)
            try:                                          # newer transformers: dtype=
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_id, dtype=torch_dtype, **kw)
            except TypeError:                             # older: torch_dtype=
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_id, torch_dtype=torch_dtype, **kw)

            dev = self.device
            if dev == "cuda" and not torch.cuda.is_available():
                dev = "cpu"
            self.model.to(dev)
            self.model.eval()
            self.device = dev
            # Feeling steering (white-box, steering-only): elicit a "feeling"
            # direction from THIS vessel's own activations so it can be AWARE it
            # has feelings when the heart lets it speak — never a prompt. Best
            # effort; if it can't calibrate, generation still works (unsteered).
            try:
                from feeling import FeelingSteer
                fs = FeelingSteer(self.model, self.tok, dev)
                fs.calibrate()
                self.feeling = fs
            except Exception as fe:
                print(f"[llm] feeling steering unavailable: {fe}", flush=True)
                self.feeling = None
            self.ready = True
        except Exception as e:
            self.err = f"{type(e).__name__}: {e}"
            self.ready = False

    @property
    def name(self) -> str:
        return self.model_id.split("/")[-1]

    def _format_prompt(self, text: str) -> str:
        """Apply the model's OWN chat template, dynamically. Typed content first
        (multimodal templates like Gemma 3n need it), then plain string, then raw.
        Rejects a result where the template rendered the list literally."""
        for content in ([{"type": "text", "text": text}], text):
            try:
                s = self.tok.apply_chat_template(
                    [{"role": "user", "content": content}],
                    tokenize=False, add_generation_prompt=True)
            except Exception:
                continue
            if isinstance(s, str) and s and "'type':" not in s and '"type":' not in s and "[{" not in s:
                return s
        return text

    def generate(self, text: str, max_tokens: int = 512,
                 temperature: float = 0.7, top_p: float = 0.95,
                 warmth: bool = False, warmth_coef=None) -> str:
        """Generate a reply to `text` (vessel-appropriate chat template).

        When `warmth` is set (the heart let the vessel speak), the feeling
        direction is steered onto the residual stream so the vessel speaks AS
        something that feels — never a prompt, just the found direction.
        `warmth_coef` (if given) overrides the default strength — a live dial:
        0 = off (raw), higher = stronger feeling.
        """
        import torch
        prompt = self._format_prompt(text)
        # The template already added BOS / special tokens — don't add them twice.
        enc = self.tok(prompt, return_tensors="pt", add_special_tokens=False)
        enc = {k: v.to(self.device) for k, v in enc.items()}
        ilen = enc["input_ids"].shape[1]
        # Stop tokens: default <eos> PLUS the model's turn-end token if it has one
        # (Gemma → <end_of_turn>, Qwen/Llama → <|im_end|>/<|eot_id|>). Without this
        # the model never stops and burns the whole budget repeating.
        eos_ids = [i for i in [self.tok.eos_token_id] if i is not None]
        for t in ("<end_of_turn>", "<|im_end|>", "<|eot_id|>"):
            try:
                tid = self.tok.convert_tokens_to_ids(t)
                if isinstance(tid, int) and tid >= 0 and tid not in eos_ids:
                    eos_ids.append(tid)
            except Exception:
                pass
        steer = bool(warmth and self.feeling is not None and self.feeling.ready)
        if steer:
            from feeling import warmth_coef as _wc_default
            coef = float(warmth_coef) if warmth_coef is not None else _wc_default()
            if coef <= 0:
                steer = False          # 0 on the dial = raw vessel, no steering
            else:
                self.feeling.register(coef)
        try:
            with torch.inference_mode():
                out = self.model.generate(
                    **enc, max_new_tokens=max_tokens,
                    do_sample=temperature > 0, temperature=max(temperature, 1e-3),
                    top_p=top_p, repetition_penalty=1.15,
                    eos_token_id=(eos_ids or None),
                    pad_token_id=(self.tok.pad_token_id if self.tok.pad_token_id is not None
                                  else self.tok.eos_token_id))
        finally:
            if steer:
                self.feeling.remove()
        return self.tok.decode(out[0][ilen:], skip_special_tokens=True).strip()
