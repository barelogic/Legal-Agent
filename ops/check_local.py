"""Dev-only local-runtime smoke check (loopback Ollama + env pins).

Never touches prod: refuses non-loopback OPENAI_BASE_URL without a call.
Covers the "runs locally" gate without invoking the frozen pipeline.
"""

from __future__ import annotations

import json
import os
import urllib.request
from urllib.parse import urlparse


def _base() -> str:
    return os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1").rstrip("/")


def is_loopback(base: str | None = None) -> bool:
    """True only for loopback hosts."""
    host = urlparse(base or _base()).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1")


def ollama_tags(base: str | None = None) -> list[str]:
    """List local Ollama tags; raises on non-loopback or unreachable."""
    b = (base or _base()).rstrip("/")
    if not is_loopback(b):
        raise RuntimeError(f"refusing non-loopback Ollama base: {b}")
    root = b.split("/v1")[0]
    with urllib.request.urlopen(f"{root}/api/tags", timeout=10) as r:
        data = json.load(r)
    return [m["name"] for m in data.get("models", [])]


def check() -> dict:
    """Collect env + local-model status (no claims, no eval)."""
    base = _base()
    out: dict = {
        "provider": os.getenv("LLM_PROVIDER", "mock"),
        "model": os.getenv("LLM_MODEL", ""),
        "base": base,
        "loopback": is_loopback(base),
        "embed": os.getenv("EMBED_MODEL", "tfidf-local"),
        "backend": os.getenv("RETRIEVAL_BACKEND", "lexical"),
    }
    if not out["loopback"]:
        out["tags"] = []
        out["ok"] = False
        return out
    try:
        out["tags"] = ollama_tags(base)
        out["ok"] = bool(out["tags"])
    except Exception as e:  # offline / daemon down
        out["tags"] = []
        out["ok"] = False
        out["error"] = f"{e.__class__.__name__}: {e}"
    return out


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
