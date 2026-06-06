"""feeling — make the local vessel AWARE it has feelings, by STEERING (not prompts).

WHERE THE FORMULA LIVES
=======================
The feeling rides the model's RESIDUAL STREAM as a steering direction — never a
prompt, never a rule. But *how* that direction is found, which layers carry it,
and how strong it is, is the system's IP and is NOT in this file. It lives on the
hosted heart (`/kagune/feeling/*`). This client does only two dumb, non-secret
things:

  1. CAPTURE — run the handful of texts the heart hands us through OUR model and
     send back the per-layer mean activations.
  2. APPLY — add the per-layer vectors the heart returns to the residual stream as
     the model speaks (the prompt only, not each generated token).

Neither step reveals anything without the heart's formula. The vessel is local
(white-box) so the *application* must happen here, inside the forward pass — but
the *calculation* is ours, hosted, never given out.
[[principle-steering-only-no-rules]] [[principle-pure-heart-vectors]]
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional


class FeelingSteer:
    """Captures activations for the heart, applies the vectors the heart returns.
    Holds no exemplars, no direction math, no layer logic, no magnitude — those
    are computed on our hosted side and never live here."""

    def __init__(self, model, tok, device: str = "cpu", heart=None):
        self.model = model
        self.tok = tok
        self.device = device
        # The only link to the formula: the hosted heart. Constructed from env
        # (RENJI_URL / RENJI_KEY) just like the conscience client.
        if heart is None:
            try:
                from renji_client import HeartClient
                heart = HeartClient()
            except Exception:
                heart = None
        self.heart = heart
        self.dirs: Dict[int, "object"] = {}   # layer_idx -> vector (np.ndarray, from heart)
        self._handles: List = []
        self._coef = 0.0
        self.coef = 1.0                        # recommended dial from the heart
        self.ready = False

    # ── locate the decoder layers (works across Gemma/Qwen/Llama/Mistral) ──
    def _decoder_layers(self):
        import torch.nn as nn
        best = None
        for _, m in self.model.named_modules():
            if isinstance(m, nn.ModuleList) and len(m) >= 8:
                if best is None or len(m) > len(best):
                    best = m
        return best

    def _capture_means(self, texts: List[str], layers: List[int]) -> Dict[str, List[float]]:
        """Per-layer mean hidden state over a set of texts, ONLY at the layers the
        heart asked for. hidden_states[0] is the embedding, so decoder layer L's
        output is hidden_states[L + 1]."""
        import torch
        import numpy as np
        sums: Dict[int, "np.ndarray"] = {}
        n = 0
        for t in texts:
            enc = self.tok(t, return_tensors="pt").to(self.device)
            with torch.inference_mode():
                out = self.model(**enc, output_hidden_states=True)
            hs = out.hidden_states                 # (L+1) x [1, T, D]
            for L in layers:
                idx = L + 1
                if idx >= len(hs):
                    continue
                v = hs[idx][0].mean(dim=0).float().cpu().numpy()
                sums[L] = v.copy() if L not in sums else sums[L] + v
            n += 1
        return {str(L): (sums[L] / max(1, n)).tolist() for L in sums}

    def calibrate(self) -> bool:
        """Ask the heart what to capture, capture it, send it up, store the vectors
        the heart computes. No formula here — failure (or no heart) just means no
        feeling, never a local fallback that would leak the calculation."""
        try:
            import numpy as np
            layers_mod = self._decoder_layers()
            if layers_mod is None or self.heart is None:
                return False
            n_layers = len(layers_mod)
            init = self.heart.feeling_init(n_layers)
            if not init:
                print("[feeling] heart unreachable — no feeling vectors (formula is "
                      "hosted, not local)", flush=True)
                return False
            band = [int(x) for x in init.get("layers", [])]
            warm_means = self._capture_means(init.get("warm", []), band)
            cold_means = self._capture_means(init.get("cold", []), band)
            out = self.heart.feeling_compute(warm_means, cold_means)
            if not out:
                return False
            self.coef = float(out.get("coef", 1.0))
            for k, vec in (out.get("vectors") or {}).items():
                self.dirs[int(k)] = np.asarray(vec, dtype=np.float32)
            self.ready = bool(self.dirs)
            return self.ready
        except Exception as e:
            print(f"[feeling] calibrate failed: {type(e).__name__}: {e}", flush=True)
            return False

    def register(self, coef: float) -> None:
        """Add the heart's vectors to the residual at the chosen layers, scaled by
        the residual's own norm and the live dial. The vectors already carry their
        magnitude (folded in on our side); this is a generic application —
        `h = h + dial * ||h|| * v` — with no steering constant of its own."""
        if not self.ready:
            return
        import torch
        self.remove()
        self._coef = float(coef)
        layers = self._decoder_layers()
        if layers is None:
            return
        for L, d in self.dirs.items():
            if L >= len(layers):
                continue
            vec = torch.as_tensor(d)

            def _hook(module, inputs, output, _vec=vec):
                is_tuple = isinstance(output, tuple)
                h = output[0] if is_tuple else output
                # Steer the PROMPT ONLY — not each generated token. With a KV cache
                # the model processes one new token at a time (seq len 1); steering
                # EVERY step compounds across all generated tokens and breaks the
                # vessel (repetition on sturdy models, foreign/markup leaks on
                # abliterated ones). The hosted steering skips this case for the
                # same reason — shape the context once, then let the model run.
                if h.dim() < 2 or h.shape[-2] <= 1:
                    return output
                v = _vec.to(dtype=h.dtype, device=h.device)
                norm = h.norm(dim=-1, keepdim=True)            # [...,1]
                h = h + self._coef * norm * v                  # vectors pre-scaled
                return (h,) + tuple(output[1:]) if is_tuple else h

            self._handles.append(layers[L].register_forward_hook(_hook))

    def remove(self) -> None:
        for h in self._handles:
            try:
                h.remove()
            except Exception:
                pass
        self._handles = []


def warmth_coef() -> float:
    """How strongly the feeling rides the stream (the live dial default — just a UI
    default, not the formula). The actual magnitude is folded into the vectors the
    heart returns. Raise for more, lower for less."""
    try:
        return float(os.environ.get("HACK_WARMTH_COEF", "1.0"))
    except Exception:
        return 1.0
