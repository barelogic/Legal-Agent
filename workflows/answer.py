"""Orchestrate retrieve -> claims -> verify -> render-or-refuse.

The LLM only produces structured claims; final text is rendered locally
FROM verified claims. Unverified claims are dropped. If none survive,
the Answer refuses with "Not found in the provided sources".

Regeneration: if more than 30% of first-attempt claims fail verification,
the LLM gets exactly one retry with the failure notes appended; the better
result (more verified claims) is kept. Skipped under MockClient, where a
retry would deterministically repeat itself.
"""

import time
from typing import Literal

from contracts.schemas import Answer, Chunk, Claim, MissingInfo
from generation.claims import generate_claims
from retrieval.store import Registry
from verify import flags as vflags
from verify.citations import build_citations
from verify.judge import is_mock_client, make_judge_client
from verify.verifier import verify_all

Workflow = Literal["chat", "draft", "review", "research"]
REFUSAL = "Not found in the provided sources"
REGEN_FAIL_FRACTION = 0.30


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
    flagset = vflags.all_flags()

    judge_client, judge_note = None, None
    if flagset["entailment"]:
        judge_client, judge_note = make_judge_client(llm)

    candidates = generate_claims(llm, question, retrieved)
    verified, failed = verify_all(
        candidates, chunk_map, docs=registry.docs, judge=judge_client, flagset=flagset
    )

    fallbacks: list[str] = []
    if judge_note is not None:
        fallbacks.append(judge_note)

    # One regeneration when the first attempt mostly fails.
    regenerated = False
    fail_frac = len(failed) / len(candidates) if candidates else 0.0
    if flagset["regenerate"] and candidates and fail_frac > REGEN_FAIL_FRACTION:
        if is_mock_client(llm):
            fallbacks.append("regenerate skipped (MockClient: retry is deterministic)")
        else:
            notes = "; ".join(f"{c.claim_id}: {c.verifier_note}" for c in failed)
            retry = generate_claims(llm, question, retrieved, retry_notes=notes)
            v2, f2 = verify_all(
                retry, chunk_map, docs=registry.docs, judge=judge_client, flagset=flagset
            )
            regenerated = True
            if len(v2) > len(verified):
                verified, failed = v2, f2

    citations = build_citations(verified, chunk_map, registry.docs)
    ms = int((time.perf_counter() - t0) * 1000)
    trace = {
        "retrieved_chunk_ids": [c.chunk_id for c in retrieved],
        "dropped": len(failed),
        "dropped_reasons": [f"{c.claim_id}: {c.verifier_note}" for c in failed],
        "fallbacks": fallbacks,
        "verify_flags": flagset,
        "regenerated": regenerated,
        "latency_ms": ms,
    }
    if not verified:
        # Refusal tristate: distinguish "nothing retrieved" from "model
        # silent" from "everything failed" (they need different fixes).
        if not retrieved:
            reason = "no retrieved chunk supported a verifiable claim"
        elif not candidates:
            reason = "model returned no claims"
        else:
            reason = "all claims failed verification"
        return Answer(
            workflow=workflow,
            text=REFUSAL,
            claims=failed,  # audit trail with unsupported statuses
            citations=[],
            missing_info=[
                MissingInfo(
                    field="supporting evidence",
                    why_needed=reason,
                    searched_in=sorted({c.doc_id for c in retrieved}),
                )
            ],
            contradictions=[],  # no contradiction detector yet; never invent
            confidence=(0.0 if candidates else None),
            refused=True,
            refusal_reason=reason,
            trace=trace,
        )
    return Answer(
        workflow=workflow,
        text=render_text(verified),
        claims=verified,  # failed stay in trace.dropped_reasons, not the payload
        citations=citations,
        missing_info=[],
        contradictions=[],
        confidence=(len(verified) / len(candidates) if candidates else None),
        refused=False,
        trace=trace,
    )
