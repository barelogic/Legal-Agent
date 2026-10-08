"""Offline demo fixtures: valid Answer objects + a chunk/doc registry.

``ui/fixtures/*.json`` are UI-owned demo data (not backend responses).
Every Answer parses against the frozen ``contracts`` schema; a test pins
that each verified quote is a verbatim substring of its cited chunk.
In fixture mode the app serves these with zero HTTP calls.
"""

from __future__ import annotations

import json
from pathlib import Path

from contracts.schemas import Answer, Chunk, Doc

FIXTURE_NAMES = ("chat", "precheck", "draft", "review", "refusal")

#: Tab workflow -> fixture served by Ask. Draft's Run-precheck uses precheck.
WORKFLOW_FIXTURE = {
    "chat": "chat",
    "draft": "draft",
    "review": "review",
    "research": "refusal",
}


def _dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


def load_answer(name: str) -> Answer:
    """Load one fixture Answer; raises ValueError if unknown/invalid."""
    if name not in FIXTURE_NAMES:
        raise ValueError(f"unknown fixture {name!r}")
    return Answer(**json.loads((_dir() / f"{name}.json").read_text(encoding="utf-8")))


def load_registry() -> tuple[list[Doc], dict[str, Chunk]]:
    """Docs + chunks backing the source panel and contradiction view."""
    raw = json.loads((_dir() / "chunks.json").read_text(encoding="utf-8"))
    docs = [Doc(**d) for d in raw["docs"]]
    chunks = {cid: Chunk(**c) for cid, c in raw["chunks"].items()}
    return docs, chunks


def get_chunk(chunk_id: str) -> Chunk:
    """Fixture chunk fetch; RuntimeError mirrors api_client.get_source."""
    _, chunks = load_registry()
    try:
        return chunks[chunk_id]
    except KeyError:
        raise RuntimeError(f"fixture has no chunk {chunk_id}") from None


def demo_provided_values(answer: Answer) -> dict[str, str]:
    """Prefill values for missing-info inputs (fixture demo metadata).

    Read from ``trace["demo_provided_values"]`` — UI-owned fixture data,
    not a backend contract. Empty in live mode.
    """
    vals = (answer.trace or {}).get("demo_provided_values", {})
    return dict(vals) if isinstance(vals, dict) else {}
