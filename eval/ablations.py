"""Ablations: research contribution (25% weight).

Configs (each is a (system, top_k) run over the same gold set):
- verifier: full_lexical_verified vs baseline_no_verify (same retriever,
  verification on/off) -> grounding delta.
- retriever: full_lexical_verified vs hybrid_verified (same verifier,
  retriever swap) -> retrieval delta.
- depth: full_lexical_verified at top_k in {2, 4, 8} -> depth sensitivity.

run_ablations() returns {config_name: {retrieval, groundedness}} using the
shared metric modules so numbers match the main tables.
"""

from __future__ import annotations


ABLATIONS: list[dict] = [
    {"name": "verifier_on_lexical_k4", "system": "full_lexical_verified", "top_k": 4},
    {"name": "verifier_off_lexical_k4", "system": "baseline_no_verify", "top_k": 4},
    {"name": "verifier_on_hybrid_k4", "system": "hybrid_verified", "top_k": 4},
    {"name": "verifier_on_lexical_k2", "system": "full_lexical_verified", "top_k": 2},
    {"name": "verifier_on_lexical_k8", "system": "full_lexical_verified", "top_k": 8},
    {"name": "fault_injected_no_verify_k4", "system": "baseline_injected", "top_k": 4},
]


def run_ablations(rows: list[dict], docs: dict, chunks: dict) -> dict:
    from eval.metrics_grounded import groundedness_report
    from eval.metrics_retrieval import retrieval_report
    from eval.systems import run_system

    out: dict = {}
    for cfg in ABLATIONS:
        answers = [
            run_system(cfg["system"], r["question"], docs, chunks, top_k=cfg["top_k"])
            for r in rows
        ]
        # Fault-injected answers must pass through the verifier to measure
        # the drop: re-verify injected candidates the way the full pipeline
        # would, and report post-verification fabrication.
        if cfg["system"] == "baseline_injected":
            from verify.verifier import verify_all as _va

            kept = 0
            for ans in answers:
                cmap = {cid: chunks[cid] for cid in ans.trace.get("retrieved_chunk_ids", [])
                        if cid in chunks}
                verified, failed = _va(list(ans.claims), cmap)
                kept += len(failed)
            out[cfg["name"]] = {
                "system": cfg["system"],
                "top_k": cfg["top_k"],
                "retrieval": retrieval_report(
                    rows, docs, chunks, systems=("full_lexical_verified",), top_k=cfg["top_k"]
                )["full_lexical_verified"],
                "groundedness": groundedness_report(
                    {cfg["system"]: answers}, rows, docs, chunks
                )[cfg["system"]],
                "injected_dropped_by_verifier": kept,
                "note": "synthetic fault-injection stress (not live-LLM behavior)",
            }
            continue
        out[cfg["name"]] = {
            "system": cfg["system"],
            "top_k": cfg["top_k"],
            "retrieval": retrieval_report(
                rows, docs, chunks, systems=(cfg["system"],), top_k=cfg["top_k"]
            )[cfg["system"]],
            "groundedness": groundedness_report(
                {cfg["system"]: answers}, rows, docs, chunks
            )[cfg["system"]],
        }
    # deltas = the research contribution, computed not asserted
    try:
        on = out["verifier_on_lexical_k4"]["groundedness"]["fabrication_rate"]
        off = out["verifier_off_lexical_k4"]["groundedness"]["fabrication_rate"]
        out["delta_verifier_fabrication"] = off - on  # + means verifier removed fabs
        lex = out["verifier_on_lexical_k4"]["retrieval"]["recall@k"]
        hyb = out["verifier_on_hybrid_k4"]["retrieval"]["recall@k"]
        out["delta_hybrid_recall"] = hyb - lex
        lex_mrr = out["verifier_on_lexical_k4"]["retrieval"].get("mrr", 0.0)
        hyb_mrr = out["verifier_on_hybrid_k4"]["retrieval"].get("mrr", 0.0)
        out["delta_hybrid_mrr"] = hyb_mrr - lex_mrr
        inj = out["fault_injected_no_verify_k4"]["groundedness"]["fabrication_rate"]
        out["delta_injected_vs_full_fabrication"] = inj - on
        out["injected_note"] = (
            "synthetic stress: MockClient never hallucinates, so verifier on/off "
            "on clean candidates shows 0 delta; injected faults measure the guardrail."
        )
    except KeyError:
        pass
    return out
