"""
remote_vessel — Mode B: generate via a SELF-HOSTED vessel you run elsewhere
===========================================================================
Instead of running the model in this folder (Mode A / llm.py), you run it on your
own GPU behind a tiny HTTP endpoint and give us its URL. This client calls it.

Contract — what you give, what we expect back:

    POST {VESSEL_URL}                       (optional: Authorization: Bearer {VESSEL_SECRET})
        { "prompt": "...", "max_tokens": 512, "temperature": 0.7, "top_p": 0.95 }
    -> { "text": "...the model's reply..." }

For convenience it also accepts OpenAI-style replies:
    { "choices": [ { "text": "..." } ] }                      (completions)
    { "choices": [ { "message": { "content": "..." } } ] }    (chat)
"""
from __future__ import annotations

import os

import httpx


class RemoteVessel:
    def __init__(self, url: str = "", secret: str = "", timeout: float = 120.0):
        self.url = (url or os.environ.get("VESSEL_URL", "")).rstrip("/")
        self.secret = secret or os.environ.get("VESSEL_SECRET", "")
        self.timeout = timeout
        self.ready = bool(self.url)
        self.err = "" if self.url else "set VESSEL_URL in .env to use a remote vessel"

    @property
    def name(self) -> str:
        return self.url or "remote-vessel (no URL)"

    @property
    def device(self) -> str:
        return "remote"

    def boot(self) -> None:
        self.ready = bool(self.url)
        if not self.url:
            self.err = "set VESSEL_URL in .env to use a remote vessel"

    def generate(self, text: str, max_tokens: int = 512,
                 temperature: float = 0.7, top_p: float = 0.95) -> str:
        headers = {"Authorization": f"Bearer {self.secret}"} if self.secret else {}
        body = {"prompt": text, "max_tokens": max_tokens,
                "temperature": temperature, "top_p": top_p}
        r = httpx.post(self.url, json=body, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        d = r.json()
        if isinstance(d, dict):
            if isinstance(d.get("text"), str):
                return d["text"].strip()
            if d.get("choices"):
                c = d["choices"][0]
                return str(c.get("text") or (c.get("message") or {}).get("content", "")).strip()
        return str(d).strip()
