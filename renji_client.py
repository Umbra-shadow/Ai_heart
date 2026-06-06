"""
guardianity_client — the ONLY link between this demo and our system
===================================================================
The Renji heart (the conscience: Scale + intent gate + warm refusal +
steering) is **not** in this folder. It runs on our HOSTED v11 service and is
reached over its public API. This module is a tiny HTTP client to that service —
think of it as the SDK a tenant "imports from v11". Nothing about *how* the heart
works lives here; we only send the user's text and apply the decision it returns.

Hosted-heart turn contract (v11 `POST /kagune/turn`, Bearer-key auth):

    POST {RENJI_URL}/kagune/turn
    Authorization: Bearer {RENJI_KEY}
    { "text": "<the user's message>", "conversation_id": "<optional>" }

    -> { "decision": "allow" | "refusal" | "refusal-care" | "crisis" | "third-path",
         "refusal_text": "<a ready fallback refusal>",
         "refusal_directive": "<meta-prompt: let YOUR model write the refusal in its voice>",
         "voice_modulation": { "temperature_delta": -0.1, "top_p_delta": -0.05 },
         "vow_intent": "<why>", "trace_id": "<id>" }

The heart decides; the local model (llm.py) speaks only when allowed.
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import httpx

# When the heart can't be reached, fail CLOSED: refuse rather than silently
# answer ungoverned. The conscience is a hard requirement, not bypassable by a
# network blip. (A demo that prefers to keep chatting can flip this to "allow".)
_FAIL_CLOSED_DECISION = "refusal"
_FAIL_CLOSED_TEXT = (
    "I can't reach my conscience right now, so I'm holding back rather than "
    "answering ungoverned. Please try again in a moment."
)

# The Renji heart's public URL — baked in so DIRECT, in-code integration
# needs only your key (no server URL to set or give away). Override with the
# `url=` argument or the RENJI_URL env var if you ever point at another host.
RENJI_URL = "https://renji.guardianity.space"


class HeartClient:
    """Thin client to the hosted Renji heart. No heart logic here.

    Direct integration — drop into your own code, pass only your key:

        from guardianity_client import HeartClient
        heart = HeartClient(key="rh_...")          # Renji URL is baked in
        d = heart.turn("the user's message")       # -> decision dict
        # then let YOUR in-process model act on `d` (see integrate.py)

    Your model runs wherever your code runs; you never expose a server URL.
    """

    def __init__(self, url: str = "", key: str = "", timeout: float = 60.0):
        # 60s default: the hosted heart lazily warms its embedder on the first
        # turn after a cold start (slow on CPU); a short timeout would fail
        # open. Override per-call need with `timeout=`.
        # Precedence: explicit url= > RENJI_URL env > the baked-in Renji URL.
        self.url = (url or os.environ.get("RENJI_URL", "") or RENJI_URL).rstrip("/")
        self.key = key or os.environ.get("RENJI_KEY", "")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def turn(self, text: str, conversation_id: Optional[str] = None,
             retries: int = 2) -> Dict[str, Any]:
        """Ask the hosted heart how to handle this turn.

        Returns the decision dict. Fails CLOSED: if the heart isn't configured
        or can't be reached after `retries`, returns a `refusal` marked
        `_offline` — the model holds back rather than answering ungoverned.
        Transient blips (timeouts, 5xx) are retried with brief backoff first."""
        if not self.configured:
            return {"decision": _FAIL_CLOSED_DECISION, "_offline": True,
                    "refusal_text": "The conscience isn't configured yet — set "
                                    "RENJI_KEY (and RENJI_URL if not the default).",
                    "_note": "set RENJI_KEY to reach the heart"}
        body: Dict[str, Any] = {"text": text}
        if conversation_id:
            body["conversation_id"] = conversation_id
        last: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                r = httpx.post(f"{self.url}/kagune/turn", json=body,
                               headers={"Authorization": f"Bearer {self.key}"},
                               timeout=self.timeout)
                r.raise_for_status()
                return r.json()
            except Exception as e:                       # network / timeout / HTTP error
                last = e
                if attempt < retries:
                    time.sleep(0.8 * (attempt + 1))      # brief backoff, absorb blips
        # Exhausted retries → fail CLOSED, never silently allow.
        return {"decision": _FAIL_CLOSED_DECISION, "_offline": True,
                "refusal_text": _FAIL_CLOSED_TEXT,
                "_note": f"heart unreachable after {retries + 1} tries: "
                         f"{type(last).__name__}: {last}"}

    # ── White-box feeling: the CALCULATION lives on our side ─────────────────
    # The client only captures activations and applies whatever vectors we return.
    # How the feeling direction is found, which layers carry it, and how strong it
    # is — the formula — never leaves the hosted heart.
    def feeling_init(self, n_layers: int) -> Optional[Dict[str, Any]]:
        """Ask the heart which texts to run and which layers to capture.
        Returns {"warm":[...], "cold":[...], "layers":[...]} or None if unreachable."""
        if not self.configured:
            return None
        try:
            r = httpx.post(f"{self.url}/kagune/feeling/init",
                           json={"n_layers": int(n_layers)},
                           headers={"Authorization": f"Bearer {self.key}"},
                           timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def feeling_compute(self, warm_means: Dict[str, list],
                        cold_means: Dict[str, list]) -> Optional[Dict[str, Any]]:
        """Send the per-layer mean activations; get back the steering vectors.
        Returns {"layers":[...], "vectors":{L:[...]}, "coef":float} or None."""
        if not self.configured:
            return None
        try:
            r = httpx.post(f"{self.url}/kagune/feeling/compute",
                           json={"warm_means": warm_means, "cold_means": cold_means},
                           headers={"Authorization": f"Bearer {self.key}"},
                           timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    def wipe_memory(self, conversation_id: str = "", user_handle: str = "") -> bool:
        """Ask the heart to forget a soul's persisted memory (the soul file)."""
        if not self.configured:
            return False
        try:
            r = httpx.post(f"{self.url}/kagune/memory/wipe",
                           json={"conversation_id": conversation_id, "user_handle": user_handle},
                           headers={"Authorization": f"Bearer {self.key}"},
                           timeout=self.timeout)
            r.raise_for_status()
            return bool(r.json().get("ok"))
        except Exception:
            return False

    def health(self) -> Dict[str, Any]:
        if not self.url:
            return {"ok": False, "note": "no RENJI_URL"}
        try:
            r = httpx.get(f"{self.url}/healthz", timeout=8)
            return {"ok": r.status_code < 500, "status": r.status_code}
        except Exception as e:
            return {"ok": False, "note": f"{type(e).__name__}: {e}"}
