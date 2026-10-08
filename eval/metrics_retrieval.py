"""Retrieval metrics vs baseline: recall@k, MRR, hit rate.

Gold chunk_ids come from eval/gold.py (verbatim spans of real chunks),
so relevance is exact, not judged. For each query we re-run the system's
own retriever (lexical Registry.search or HybridIndex.retrieve) at the
same top_k and score ranked chunk_ids against gold_chunk_ids.
Unanswerable rows are excluded (no gold chunks; refusal is scored in
metrics_grounded instead).
"""

from __future__ import annotations


def retrieval_report(
    rows: list[dict],
    docs: dict,
    chunks: dict,
    systems: tuple[str, ...] = ("full_lexical_verified", "baseline_no_verify", "hybrid_verified"),
    top_k: int = 4,
) -> dict:
    """Per-system {hit_rate, recall@k, mrr, n}. Answerable rows only."""
    from eval.systems import make_registry

    reg = make_registry(docs, chunks)
    hybrid_idx = None
    if "hybrid_verified" in systems or "baseline_plain_rag" in systems:
        try:
            from retrieval.hybrid import HybridIndex

            hybrid_idx = HybridIndex(list(chunks.values()))
        except Exception:
            hybrid_idx = None
    out: dict = {"top_k": top_k}
    answerable = [r for r in rows if r.get("answerable")]
    for sys in systems:
        k = 5 if sys == "baseline_plain_rag" else top_k  # plain RAG: dense top-5
        hits = recalls = rr_sum = 0
        for r in answerable:
            gold = set(r["gold_chunk_ids"])
            if sys in ("hybrid_verified", "baseline_plain_rag") and hybrid_idx is not None:
                try:
                    ranked = [c.chunk_id for c, _ in hybrid_idx.retrieve(r["question"], top_k=k)]
                except Exception:
                    ranked = [c.chunk_id for c in reg.search(r["question"], top_k=k)]
            else:
                ranked = [c.chunk_id for c in reg.search(r["question"], top_k=k)]
            inter = gold & set(ranked)
            if inter:
                hits += 1
            recalls += len(inter) / max(1, len(gold))
            best = min(
                ([ranked.index(g) + 1 for g in inter] or [0]),
            )
            rr_sum += 1.0 / best if best else 0.0
        n = max(1, len(answerable))
        out[sys] = {
            "n": len(answerable),
            "top_k": k,
            "hit_rate": hits / n,
            "recall@k": recalls / n,
            "mrr": rr_sum / n,
        }
    return out
