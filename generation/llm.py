"""Provider-agnostic LLM client.

Contract: the model NEVER writes free-text facts. It only returns
structured claim candidates (text + chunk_ids + verbatim quote).
Free text is rendered locally FROM verified claims (see workflows/answer.py).
"""

import json
import os
import re
from typing import Protocol

import requests
from contracts.schemas import Chunk


class LLMClient(Protocol):
    def complete_claims(self, prompt: str) -> str:
        """Return raw model output (expected JSON array)."""
        ...


class MockClient:
    """Deterministic offline client used for tests/demo without a key."""

    def __init__(self, chunks: list[Chunk] | None = None) -> None:
        self._chunks = chunks or []

    # Abbreviations whose trailing "." never ends a sentence (P2's planted
    # texts break on "No. " without this: claim becomes "FIR No").
    _ABBREV = frozenset(
        "no rs st mr mrs ms dr v vs sr jr esp viz inc ltd co fig nos ss s".split()
    )

    def complete_claims(self, prompt: str) -> str:
        out = []
        for i, ch in enumerate(self._chunks):
            # First sentence (split on ". " so "v. CBI" doesn't cut early).
            parts = ch.text.split(". ")
            first = parts[0].strip()
            k = 1
            tail = (first.split() or [""])[-1].rstrip(".").lower()
            while k < len(parts) and (re.search(r"\b[vV]$", first) or tail in self._ABBREV):
                first = (first + ". " + parts[k]).strip()
                k += 1
                tail = (first.split() or [""])[-1].rstrip(".").lower()
            text = first[:280].rsplit(" ", 1)[0] if len(first) > 280 else first
            quote = text[:180].rsplit(" ", 1)[0] if len(text) > 180 else text
            if not quote or quote not in ch.text:  # keep verbatim guarantee
                quote = ch.text[:180].rsplit(" ", 1)[0]
                text = quote
            if not text:
                continue
            out.append(
                {
                    "text": text,
                    "chunk_ids": [ch.chunk_id],
                    "quote": quote,
                }
            )
        return json.dumps(out)


class GeminiClient:
    """Minimal Gemini REST client (generateContent). No SDK dependency."""

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 temperature: float | None = None) -> None:
        from generation.config import get_llm_temperature

        self.model = model or os.getenv("LLM_MODEL", "gemini-2.0-flash")
        self.temperature = get_llm_temperature() if temperature is None else temperature
        self.api_key = api_key if api_key is not None else (
            os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        )
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set")

    def complete_claims(self, prompt: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        body: dict = {"contents": [{"parts": [{"text": prompt}]}]}
        if self.temperature is not None:
            body["generationConfig"] = {"temperature": self.temperature}
        r = requests.post(url, json=body, timeout=60)
        r.raise_for_status()
        data = r.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"unexpected Gemini response: {data!r:.500}") from e


class OpenAICompatibleClient:
    """Any OpenAI-compatible /chat/completions endpoint."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
    ) -> None:
        from generation.config import get_llm_temperature

        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL",
                                                 "https://api.openai.com/v1")).rstrip("/")
        self.temperature = get_llm_temperature() if temperature is None else temperature
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")

    def complete_claims(self, prompt: str) -> str:
        r = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.temperature,
            },
            timeout=60,
        )
        r.raise_for_status()
        try:
            return r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(
                f"unexpected OpenAI-compatible response: {r.text[:500]!r}"
            ) from e


def make_client(chunks_for_mock: list[Chunk] | None = None) -> LLMClient:
    """Factory honoring LLM_PROVIDER / LLM_MODEL env vars."""
    from generation.config import get_llm_model, get_llm_provider

    provider = get_llm_provider()
    if provider == "gemini":
        return GeminiClient(model=get_llm_model())
    if provider in ("openai_compatible", "openai"):
        return OpenAICompatibleClient(model=get_llm_model())
    return MockClient(chunks=chunks_for_mock or [])
