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
"""

from __future__ import annotations


def _norm(s: str) -> str:
    return " ".join(s.split()).casefold()


def quote_supported(quote: str, chunk_texts: list[str]) -> bool:
    nq = _norm(quote)
    return bool(nq) and any(nq in _norm(t) for t in chunk_texts)


def groundedness_report(
    answers_by_system: dict[str, list],
    rows: list[dict],
    docs: dict,
    chunks: dict,
) -> dict:
    """answers_by_system[sys] aligns 1:1 with rows. Returns per-system dict."""
    out: dict = {}
    for sys, answers in answers_by_system.items():
        n_ans = fab = refused_ok = 0
        n_answerable = n_unanswer = refused_total = 0
        ver_count = cite_ok = cite_total = 0
        for row, ans in zip(rows, answers):
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
                    n_ans += 1
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
        out[sys] = {
            "n": len(rows),
            "n_answerable": n_answerable,
            "n_unanswerable": n_unanswer,
            "verified_rate": ver_count / max(1, n_answerable),
            "citation_resolved_rate": (cite_ok / cite_total) if cite_total else 1.0,
            "refusal_recall": (refused_ok / n_unanswer) if n_unanswer else 1.0,
            "refusal_precision": (refused_ok / refused_total) if refused_total else 1.0,
            "fabrication_rate": fab / n,
        }
    return out
