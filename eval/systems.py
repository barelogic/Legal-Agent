"""Systems under test: baseline(s) vs grounded pipeline.

Uses contracts/schemas.py exactly (Doc, Chunk, Answer, Claim). No schema edits.

- full_lexical_verified: Phase-1 default. Registry.search + generate_claims
  (MockClient, deterministic offline) + verify_all + render-or-refuse.
- baseline_no_verify: SAME retriever, verification SKIPPED. Raw claim
  candidates are rendered directly. Isolates the grounding gain; any
  unsupported quote that full drops but baseline keeps is the effect size.
- hybrid_verified: HybridIndex.retrieve + answer_from_chunks + verify.
  Falls back to lexical when ML libs are absent (still a valid ablation:
  reports backend used per query in trace).

All systems share the MockClient so numbers are reproducible with one
command and offline. Live-LLM runs remain possible via env but are NOT
the reported numbers (write-up must say which client produced each table).
"""

from __future__ import annotations

import time
from typing import Literal

from contracts.schemas import Answer, Chunk, Claim, Doc
from generation.claims import generate_claims
from generation.llm import MockClient
from retrieval.store import Registry
from verify.citations import build_citations
from verify.verifier import verify_all
from workflows.answer import REFUSAL, answer_from_chunks, render_text

SystemName = Literal[
    "full_lexical_verified", "baseline_no_verify", "hybrid_verified",
    "baseline_injected",
]

INJECTED_TEXT = "The court awarded punitive damages of Rs. 999 crore."
INJECTED_QUOTE = "punitive damages of Rs. 999 crore ordered by the moon court"


def make_registry(docs: dict[str, Doc], chunks: dict[str, Chunk]) -> Registry:
    reg = Registry()
    for d in docs.values():
        reg.register_doc(d)
    reg.add_chunks(list(chunks.values()))
    return reg


def run_system(
    system: SystemName,
    question: str,
    docs: dict[str, Doc],
    chunks: dict[str, Chunk],
    top_k: int = 4,
    workflow: str = "chat",
) -> Answer:
    """Run one system on one question. Deterministic (MockClient)."""
    reg = make_registry(docs, chunks)
    llm = MockClient()
    t0 = time.perf_counter()
    if system == "hybrid_verified":
        try:
            from retrieval.hybrid import HybridIndex

            idx = HybridIndex(list(chunks.values()))
            hits = idx.retrieve(question, top_k=top_k)
            retrieved = [c for c, _ in hits]
            ans = answer_from_chunks(question, workflow, reg, llm, retrieved, t0=t0)  # type: ignore[arg-type]
            ans.trace["backend"] = "hybrid"
            return ans
        except Exception as e:
            retrieved = reg.search(question, top_k=top_k)
            ans = answer_from_chunks(question, workflow, reg, llm, retrieved, t0=t0)  # type: ignore[arg-type]
            ans.trace["backend"] = f"hybrid-fallback-lexical:{e.__class__.__name__}"
            return ans
    retrieved: list[Chunk] = reg.search(question, top_k=top_k)
    chunk_map = {c.chunk_id: c for c in retrieved}
    candidates = generate_claims(llm, question, retrieved)
    if system == "baseline_injected":
        # Synthetic stress: simulate a hallucinating LLM by appending one
        # fabricated claim (fake quote, real chunk_id). The verifier must
        # drop it; the no-verify baseline keeps it. Labeled as synthetic.
        if retrieved:
            candidates.append(
                Claim(
                    claim_id=f"c{len(candidates) + 1}",
                    text=INJECTED_TEXT,
                    chunk_ids=[retrieved[0].chunk_id],
                    quote=INJECTED_QUOTE,
                )
            )
        ms = int((time.perf_counter() - t0) * 1000)
        trace = {
            "retrieved_chunk_ids": [c.chunk_id for c in retrieved],
            "dropped": 0,
            "latency_ms": ms,
            "backend": "lexical",
            "unverified": True,
            "fault_injected": True,
        }
        if not candidates:
            return Answer(
                workflow=workflow,  # type: ignore[arg-type]
                text=REFUSAL,
                claims=[],
                citations=[],
                refused=True,
                refusal_reason="no candidates (empty retrieval)",
                trace=trace,
            )
        for cl in candidates:
            cl.status = "unverified"
        citations = build_citations(candidates, chunk_map, reg.docs)
        return Answer(
            workflow=workflow,  # type: ignore[arg-type]
            text=render_text(candidates),
            claims=candidates,
            citations=citations,
            refused=False,
            trace=trace,
        )
    if system == "baseline_no_verify":
        ms = int((time.perf_counter() - t0) * 1000)
        trace = {
            "retrieved_chunk_ids": [c.chunk_id for c in retrieved],
            "dropped": 0,
            "latency_ms": ms,
            "backend": "lexical",
            "unverified": True,
        }
        if not candidates:
            return Answer(
                workflow=workflow,  # type: ignore[arg-type]
                text=REFUSAL,
                claims=[],
                citations=[],
                refused=True,
                refusal_reason="no candidates (empty retrieval)",
                trace=trace,
            )
        for cl in candidates:
            cl.status = "unverified"
        citations = build_citations(candidates, chunk_map, reg.docs)
        return Answer(
            workflow=workflow,  # type: ignore[arg-type]
            text=render_text(candidates),
            claims=candidates,
            citations=citations,
            refused=False,
            trace=trace,
        )
    # full_lexical_verified == Phase-1 path
    ans = answer_from_chunks(question, workflow, reg, llm, retrieved, t0=t0)  # type: ignore[arg-type]
    ans.trace["backend"] = "lexical"
    return ans
