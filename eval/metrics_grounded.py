"""Groundedness metrics vs baseline (35% weight).

Independent re-check (does NOT trust pipeline status flags):
- quote_exact: every surviving claim's quote is a verbatim substring of a
  cited chunk (whitespace-normalized, case-insensitive — same rule as
  verify/verifier.py, re-implemented here so the metric is independent).
- citation_resolved: every citation resolves to a Doc in the registry.
- verified_rate: share of answers with >=1 surviving claim on answerables.
- refusal_recall: share of unanswerables correctly refused.
- refusal_precision: share of refusals that were truly unanswerable.
- fabrication_rate: answerable+unanswerable answers containing a claim
  that fails quote_exact (single failure = hard fail in judging).

Baseline comparison: full - baseline_no_verify deltas are the grounding gain.
baseline_plain_rag is scored differently (it has no claims/verifier by
design): eval-time atomic-claim extraction + independent-judge verdicts
(see eval/plain_rag.py). Its trace carries the precomputed eval so this
report stays a pure read (recomputed on demand if missing).

Extra per-system keys (all systems):
- fabrication_count: answers containing >=1 unsupported claim/citation.
- trap_refusal_recall: share of trap rows refused (trap flag when present,
  else unanswerables). Traps are the refusal stress set.
- latency_ms_mean: mean answer latency from trace["latency_ms"].
- groundedness: mean atomic-claim support rate (plain RAG only; the
  pipeline systems report verified_rate instead).
"""

from __future__ import annotations


def _norm(s: str) -> str:
    return " ".join(s.split()).casefold()


def quote_supported(quote: str, chunk_texts: list[str]) -> bool:
    nq = _norm(quote)
    return bool(nq) and any(nq in _norm(t) for t in chunk_texts)


def _trap_rows(rows: list[dict]) -> list[int]:
    """Indices of trap rows; falls back to unanswerables when flag absent."""
    idx = [i for i, r in enumerate(rows) if r.get("trap") is True]
    if idx:
        return idx
    return [i for i, r in enumerate(rows) if not r.get("answerable")]


def _plain_eval(ans, docs: dict, chunks: dict) -> dict:
    """Precomputed eval from trace, recomputed on demand if missing."""
    ev = (ans.trace or {}).get("plain_rag_eval")
    if isinstance(ev, dict) and "fabrication" in ev:
        return ev
    from eval.plain_rag import evaluate_plain_answer

    cids = (ans.trace or {}).get("retrieved_chunk_ids", [])
    retrieved = [chunks[c] for c in cids if c in chunks]
    return evaluate_plain_answer(ans.text, list(ans.citations), retrieved, docs)


def groundedness_report(
    answers_by_system: dict[str, list],
    rows: list[dict],
    docs: dict,
    chunks: dict,
) -> dict:
    """answers_by_system[sys] aligns 1:1 with rows. Returns per-system dict.

    Denominator convention (deliberate, not a bug): verified_rate is over
    answerables, but fabrication_rate is over ALL rows — a single fabricated
    claim on any row is a hard fail. `unverified` pipeline claims count as
    surviving (baselines mark candidates unverified) and are re-checked
    against chunk text independently of pipeline status flags.
    """
    out: dict = {}
    trap_idx = set(_trap_rows(rows))
    trap_def = ("trap-flag" if any(r.get("trap") is True for r in rows)
                else "unanswerable-fallback")
    for sys, answers in answers_by_system.items():
        fab = refused_ok = 0
        n_answerable = n_unanswer = refused_total = 0
        ver_count = cite_ok = cite_total = 0
        lat_sum = lat_n = 0
        trap_refused = 0
        ground_sum = 0.0
        ground_n = 0
        for i, (row, ans) in enumerate(zip(rows, answers)):
            ms = (ans.trace or {}).get("latency_ms")
            if isinstance(ms, (int, float)):
                lat_sum += ms
                lat_n += 1
            if i in trap_idx and ans.refused:
                trap_refused += 1
            if sys == "baseline_plain_rag":
                ev = _plain_eval(ans, docs, chunks)
                if row.get("answerable"):
                    n_answerable += 1
                    ground_sum += ev["groundedness"]
                    ground_n += 1
                    if not ans.refused and ev["n_claims"] > 0:
                        ver_count += 1
                    if ev["fabrication"]:
                        fab += 1
                    for ci in ans.citations:
                        cite_total += 1
                        if ci.doc_id in docs and ci.resolved:
                            cite_ok += 1
                else:
                    n_unanswer += 1
                    if ans.refused:
                        refused_ok += 1
                    elif ev["fabrication"]:
                        fab += 1
                if ans.refused:
                    refused_total += 1
                continue
            if row.get("answerable"):
                n_answerable += 1
                surviving = [c for c in ans.claims if c.status in ("verified", "unverified")]
                # baseline marks unverified; full marks verified — count either
                # as "surviving", then independently re-check the quote.
                if not ans.refused and surviving:
                    ver_count += 1
                for cl in surviving:
                    texts = [chunks[cid].text for cid in cl.chunk_ids if cid in chunks]
                    if not quote_supported(cl.quote, texts):
                        fab += 1
                        break
                for ci in ans.citations:
                    cite_total += 1
                    if ci.doc_id in docs and ci.resolved:
                        cite_ok += 1
            else:
                n_unanswer += 1
                if ans.refused:
                    refused_ok += 1
                else:
                    for cl in ans.claims:
                        texts = [chunks[cid].text for cid in cl.chunk_ids if cid in chunks]
                        if cl.status in ("verified", "unverified") and not quote_supported(
                            cl.quote, texts
                        ):
                            fab += 1
                            break
            if ans.refused:
                refused_total += 1
        n = max(1, len(rows))
        n_trap = max(1, len(trap_idx))
        out[sys] = {
            "n": len(rows),
            "n_answerable": n_answerable,
            "n_unanswerable": n_unanswer,
            "verified_rate": ver_count / max(1, n_answerable),
            "citation_resolved_rate": (cite_ok / cite_total) if cite_total else 1.0,
            "refusal_recall": (refused_ok / n_unanswer) if n_unanswer else 1.0,
            "refusal_precision": (refused_ok / refused_total) if refused_total else 1.0,
            "fabrication_rate": fab / n,
            "fabrication_count": fab,
            "trap_refusal_recall": trap_refused / n_trap,
            "n_traps": len(trap_idx),
            "trap_def": trap_def,
            "latency_ms_mean": (lat_sum / lat_n) if lat_n else None,
        }
        if sys == "baseline_plain_rag":
            out[sys]["groundedness"] = (ground_sum / ground_n) if ground_n else 1.0
    return out
