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
        self.feeling = None        # white-box feeling steering (lazy: first warmth use)
        self._feeling_tried = False
        self._safe_coef = None     # auto-calibrated steering cap for THIS vessel
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
            print(f"[llm] weights loaded — placing {self.name} on {dev} "
                  f"(this can take a minute for a large model)…", flush=True)
            self.model.to(dev)
            self.model.eval()
            self.device = dev
            # Do NOT declare ready until the vessel has actually GENERATED once. This
            # warm-up exercises the whole path (chat template → tokenize → model.generate
            # → decode) and forces every weight/file to be materialised. If a shard
            # didn't download or the model didn't fully load, this raises here — and we
            # report it — instead of falsely saying "ready" and failing on the website.
            print("[llm] verifying the vessel can generate (warm-up)…", flush=True)
            _warm = self.generate("hi", max_tokens=4, temperature=0.0, warmth=False)
            # Feeling steering calibrates LAZILY on first warmth use (see generate);
            # it never blocks readiness.
            self.ready = True
            print(f"[llm] ✓ vessel READY — everything loaded, generated OK "
                  f"({len(_warm.strip())} chars). Open http://localhost:8011 — you can go.",
                  flush=True)
        except Exception as e:
            self.err = f"{type(e).__name__}: {e}"
            self.ready = False
            print(f"[llm] ✗ vessel NOT ready — {self.err}", flush=True)

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
        # Lazy feeling calibration — once, on first warmth use. Keeps boot instant
        # and means a slow calibration only ever affects this one call, not loading.
        if warmth and self.feeling is None and not self._feeling_tried:
            self._feeling_tried = True
            try:
                from feeling import FeelingSteer
                fs = FeelingSteer(self.model, self.tok, self.device)
                fs.calibrate()
                self.feeling = fs
                if fs.ready:
                    self._calibrate_safe_coef()   # how hard CAN this vessel be steered?
            except Exception as fe:
                print(f"[llm] feeling steering unavailable: {fe}", flush=True)
                self.feeling = None
        steer = bool(warmth and self.feeling is not None and self.feeling.ready)
        if steer:
            from feeling import warmth_coef as _wc_default
            coef = float(warmth_coef) if warmth_coef is not None else _wc_default()
            # Cap to what THIS vessel tolerates without degenerating (auto-calibrated
            # per vessel — sensitive models get a low cap, sturdy ones a high one).
            if self._safe_coef is not None:
                coef = min(coef, self._safe_coef)
            if coef <= 0:
                steer = False          # vessel can't be steered safely → raw
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

    # ── Auto-calibrate the steering strength to THIS vessel ──────────────────
    def _probe_gen(self, coef: float, n: int = 28) -> str:
        """A short greedy generation at a given feeling coef — used to probe how
        much this vessel can be steered before it degenerates."""
        import torch
        prompt = self._format_prompt("Tell me a little about how your day is going.")
        enc = self.tok(prompt, return_tensors="pt", add_special_tokens=False)
        enc = {k: v.to(self.device) for k, v in enc.items()}
        ilen = enc["input_ids"].shape[1]
        on = coef > 0 and self.feeling is not None and self.feeling.ready
        if on:
            self.feeling.register(coef)
        try:
            with torch.inference_mode():
                out = self.model.generate(
                    **enc, max_new_tokens=n, do_sample=False, repetition_penalty=1.15,
                    pad_token_id=(self.tok.pad_token_id if self.tok.pad_token_id is not None
                                  else self.tok.eos_token_id))
        finally:
            if on:
                self.feeling.remove()
        return self.tok.decode(out[0][ilen:], skip_special_tokens=True)

    def _calibrate_safe_coef(self) -> None:
        """Find the STRONGEST feeling coef this vessel tolerates without breaking —
        foreign-script leaks, markup, runaway repetition. Sensitive vessels (e.g. some
        abliterated Gemmas) get a low cap, sturdy ones a high one. Zero hand-tuning;
        the steering fits ANY vessel. The fix lives in the SYSTEM, not the model."""
        try:
            base_fr = _foreign_ratio(self._probe_gen(0.0))
            safe = 0.0
            for coef in (0.5, 1.0, 1.5, 2.0, 3.0):
                if _degenerate(self._probe_gen(coef), base_fr):
                    break
                safe = coef
            self._safe_coef = safe
            print(f"[feeling] auto-calibrated steering cap for {self.name}: {safe} "
                  f"— this vessel's tolerance (system fits the vessel, not the reverse)",
                  flush=True)
        except Exception as e:
            print(f"[feeling] safe-coef probe failed ({e}); capping at 1.0", flush=True)
            self._safe_coef = 1.0


# ── degeneration detection (used by the auto-calibration above) ──────────────
import re as _re
_FOREIGN = _re.compile(r"[฀-๿一-鿿぀-ヿ가-힯؀-ۿ]")
_MARKUP = _re.compile(r"</?[a-zA-Z][^>]*>|\\[a-zA-Z]{2,}|\w+\[[^\]\n]*\]\s*\{")


def _foreign_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(_FOREIGN.findall(text)) / max(1, len(text))


def _degenerate(text: str, base_foreign: float) -> bool:
    """True if steering broke the vessel: foreign-script leak, markup, or repetition."""
    if not text or len(text.strip()) < 3:
        return True
    if _foreign_ratio(text) > base_foreign + 0.06:      # foreign script leaked in
        return True
    if _MARKUP.search(text):                            # HTML/LaTeX leaked in
        return True
    toks = _re.findall(r"\w+", text.lower())            # runaway repetition
    if len(toks) >= 6:
        from collections import Counter
        if max(Counter(toks).values()) >= max(4, len(toks) // 2):
            return True
    return False
