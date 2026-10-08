"""Typed HTTP client for the grounded legal-agent mock API.

All responses are parsed into ``contracts`` Pydantic models so the UI
can never drift from the frozen schema. No display logic lives here.
"""

from __future__ import annotations

import os
from typing import Literal

import httpx

from contracts.schemas import Answer, Chunk, Doc

Workflow = Literal["chat", "draft", "review", "research"]

DEFAULT_BASE_URL = "http://localhost:8000"


def base_url(env: str | None = None) -> str:
    """Resolve API base URL (explicit arg > env > default)."""
    return (env or os.getenv("API_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")


def get_health(base: str = DEFAULT_BASE_URL, timeout: float = 5.0) -> dict:
    """Return ``/health`` payload; raises RuntimeError on failure."""
    try:
        r = httpx.get(f"{base.rstrip('/')}/health", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise RuntimeError(f"backend unreachable at {base}: {e}") from e


def list_docs(base: str = DEFAULT_BASE_URL, timeout: float = 10.0) -> list[Doc]:
    """Return registry Docs from ``GET /documents``."""
    try:
        r = httpx.get(f"{base.rstrip('/')}/documents", timeout=timeout)
        r.raise_for_status()
        return [Doc(**d) for d in r.json().get("docs", [])]
    except Exception as e:
        raise RuntimeError(f"GET /documents failed at {base}: {e}") from e


def post_answer(
    question: str,
    workflow: Workflow = "chat",
    top_k: int | None = None,
    doc_ids: list[str] | None = None,
    precheck: bool = False,
    provided_values: dict[str, str] | None = None,
    draft_type: str | None = None,
    doc_types: list[str] | None = None,
    base: str = DEFAULT_BASE_URL,
    timeout: float = 60.0,
) -> Answer:
    """POST /answer and parse the body as an ``Answer`` model.

    ``precheck`` / ``provided_values`` are forward-compatible draft keys:
    sent when set, but the current backend ``AskIn`` (``api/main.py``) has
    no such fields, so the server ignores them and the UI derives precheck
    displays client-side from the returned Answer. The redraft screen says
    this outright instead of pretending the values were consumed.
    """
    payload: dict = {"question": question, "workflow": workflow}
    if top_k is not None:
        payload["top_k"] = top_k
    if doc_ids:
        payload["doc_ids"] = doc_ids
    if precheck:
        payload["precheck"] = True
    if provided_values:
        payload["provided_values"] = provided_values
    if draft_type:
        payload["draft_type"] = draft_type
    if doc_types:
        payload["doc_types"] = doc_types
    try:
        r = httpx.post(f"{base.rstrip('/')}/answer", json=payload, timeout=timeout)
        r.raise_for_status()
        return Answer(**r.json())
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get("detail", e.response.text)
        except Exception:
            detail = e.response.text
        raise RuntimeError(f"POST /answer rejected: {detail}") from e
    except Exception as e:
        raise RuntimeError(f"POST /answer failed at {base}: {e}") from e


def get_source(
    chunk_id: str,
    base: str = DEFAULT_BASE_URL,
    timeout: float = 10.0,
) -> Chunk:
    """GET /sources/{chunk_id}; raises RuntimeError when unavailable.

    Callers must fall back to the verified quote embedded in the Answer.
    """
    try:
        r = httpx.get(f"{base.rstrip('/')}/sources/{chunk_id}", timeout=timeout)
        r.raise_for_status()
        return Chunk(**r.json())
    except Exception as e:
        raise RuntimeError(f"GET /sources/{chunk_id} failed at {base}: {e}") from e


def post_ingest(
    filename: str,
    content: bytes,
    doc_type: str,
    base: str = DEFAULT_BASE_URL,
    timeout: float = 120.0,
) -> dict:
    """POST /ingest a .pdf/.txt file; returns server summary dict."""
    try:
        r = httpx.post(
            f"{base.rstrip('/')}/ingest",
            files={"file": (filename, content)},
            data={"doc_type": doc_type},
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get("detail", e.response.text)
        except Exception:
            detail = e.response.text
        raise RuntimeError(f"POST /ingest rejected: {detail}") from e
    except Exception as e:
        raise RuntimeError(f"POST /ingest failed at {base}: {e}") from e
