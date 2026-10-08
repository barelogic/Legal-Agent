"""Orchestrate retrieve -> claims -> verify -> render-or-refuse.

The LLM only produces structured claims; final text is rendered locally
FROM verified claims. Unverified claims are dropped. If none survive,
the Answer refuses with "Not found in the provided sources".
"""

import time
from typing import Literal

from contracts.schemas import Answer, Chunk, Claim
from generation.claims import generate_claims
from retrieval.store import Registry
from verify.citations import build_citations
from verify.verifier import verify_all

Workflow = Literal["chat", "draft", "review", "research"]
REFUSAL = "Not found in the provided sources"


def render_text(claims: list[Claim]) -> str:
    """Render final text purely from verified claims (no model free text)."""
    lines = [f"- {c.text} [{c.claim_id}]" for c in claims]
    lines.append("")
    lines.append("Sources:")
    for c in claims:
        lines.append(f"[{c.claim_id}] {', '.join(c.chunk_ids)}: \"{c.quote}\"")
    return "\n".join(lines)


def answer_question(
    question: str,
    workflow: Workflow,
    registry: Registry,
    llm,
    top_k: int = 4,
) -> Answer:
    """Full grounded pipeline returning an Answer model."""
    t0 = time.perf_counter()
    retrieved: list[Chunk] = registry.search(question, top_k=top_k)
    return answer_from_chunks(question, workflow, registry, llm, retrieved, t0=t0)


def answer_from_chunks(
    question: str,
    workflow: Workflow,
    registry: Registry,
    llm,
    retrieved: list[Chunk],
    t0: float | None = None,
) -> Answer:
    """Grounded pipeline over pre-retrieved chunks (e.g. hybrid retrieval)."""
    t0 = t0 if t0 is not None else time.perf_counter()
    chunk_map = {c.chunk_id: c for c in retrieved}
    candidates = generate_claims(llm, question, retrieved)
    verified, failed = verify_all(candidates, chunk_map)
    citations = build_citations(verified, chunk_map, registry.docs)
    ms = int((time.perf_counter() - t0) * 1000)
    trace = {
        "retrieved_chunk_ids": [c.chunk_id for c in retrieved],
        "dropped": len(failed),
        "latency_ms": ms,
    }
    if not verified:
        all_claims = failed  # keep audit trail with unsupported statuses
        return Answer(
            workflow=workflow,
            text=REFUSAL,
            claims=all_claims,
            citations=[],
            refused=True,
            refusal_reason=(
                "no retrieved chunk supported a verifiable claim"
                if not retrieved else "all claims failed verification"
            ),
            trace=trace,
        )
    return Answer(
        workflow=workflow,
        text=render_text(verified),
        claims=verified + failed,
        citations=citations,
        refused=False,
        trace=trace,
    )
