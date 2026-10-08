"""Build the claims-only prompt and parse the model output into Claims.

The model must output a JSON array of {text, chunk_ids, quote} and nothing
else. No free-text facts are accepted from the model.
"""

import json
import re

from contracts.schemas import Chunk, Claim


SYSTEM_RULES = """You are a legal assistant. You MUST NOT use memory of laws or cases.
Use ONLY the SOURCES below. Output ONLY a JSON array, no prose.
Each item: {"text": "one atomic factual statement", "chunk_ids": ["<chunk_id>"], "quote": "<verbatim span copied exactly from a cited chunk>"}.
Rules: quote must be an exact substring of one cited chunk; chunk_ids must come from SOURCES; if the answer is not in SOURCES, output []."""


def build_prompt(question: str, chunks: list[Chunk]) -> str:
    """Render sources + question into a claims-extraction prompt."""
    src = "\n\n".join(f"[{c.chunk_id}] ({c.doc_id}) {c.text}" for c in chunks)
    return (
        f"{SYSTEM_RULES}\n\nSOURCES:\n{src}\n\nQUESTION: {question}\n\nJSON array only:"
    )


def _strip_fences(raw: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    return m.group(1).strip() if m else raw.strip()


def parse_claims(raw: str) -> list[Claim]:
    """Parse raw JSON into unverified Claim models. Invalid items are skipped."""
    text = _strip_fences(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = data.get("claims", data.get("data", []))
    if not isinstance(data, list):
        return []
    claims: list[Claim] = []
    for i, item in enumerate(data, 1):
        if not isinstance(item, dict):
            continue
        try:
            claims.append(
                Claim(
                    claim_id=f"c{i}",
                    text=str(item.get("text", "")).strip(),
                    chunk_ids=list(item.get("chunk_ids", []) or []),
                    quote=str(item.get("quote", "")),
                )
            )
        except Exception:
            continue
    return claims


def generate_claims(llm, question: str, chunks: list[Chunk]) -> list[Claim]:
    """Call the LLM and return parsed (still unverified) claims."""
    # MockClient emits one candidate per bound chunk: always bind exactly the
    # *retrieved* chunks so empty retrieval -> no candidates -> refusal.
    if hasattr(llm, "_chunks"):
        try:
            llm._chunks = chunks  # type: ignore[attr-defined]
        except Exception:
            pass
    prompt = build_prompt(question, chunks)
    raw = llm.complete_claims(prompt)
    return parse_claims(raw)
