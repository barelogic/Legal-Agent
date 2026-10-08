"""Plain-RAG baseline tests (offline, deterministic fallback)."""

from contracts.schemas import Citation
from eval.corpus_sources import corpus_registry
from eval.metrics_grounded import groundedness_report
from eval.metrics_retrieval import retrieval_report
from eval.plain_rag import (
    PLAIN_RAG_TOP_K,
    evaluate_plain_answer,
    extract_atomic_claims,
    judge_claim_supported,
    parse_plain_citations,
    retrieve_top5,
)
from eval.systems import run_system


def _seeds():
    return corpus_registry(hf_limit=0)


def test_plain_rag_runs_offline_with_mode_logged():
    docs, chunks = _seeds()
    ans = run_system("baseline_plain_rag", "bail in non-bailable offences?",
                     docs, chunks)
    assert not ans.refused
    assert ans.text
    assert ans.trace["top_k"] == PLAIN_RAG_TOP_K == 5
    assert ans.trace["backend"].startswith(("hybrid", "lexical"))
    assert "llm_mode" in ans.trace  # live vs mock-fallback always logged
    assert "plain_rag_eval" in ans.trace


def test_plain_rag_refuses_empty_retrieval():
    docs, chunks = _seeds()
    ans = run_system("baseline_plain_rag", "xyzzy quantum torts on Mars",
                     docs, chunks)
    assert ans.refused


def test_unresolved_citation_is_fabrication():
    docs, chunks = _seeds()
    retrieved = list(chunks.values())[:2]
    cits = [Citation(cite_id="no_such_doc", raw="no_such_doc",
                     doc_id=None, resolved=False)]
    ev = evaluate_plain_answer(retrieved[0].text, cits, retrieved, docs)
    assert ev["unresolved_citations"] == 1
    assert ev["fabrication"] is True


def test_verbatim_copy_judged_supported_offline():
    docs, chunks = _seeds()
    retrieved = list(chunks.values())[:2]
    cits = parse_plain_citations(retrieved[0].text, docs, retrieved)
    ev = evaluate_plain_answer(retrieved[0].text, cits, retrieved, docs)
    assert ev["n_claims"] >= 1
    assert ev["fabrication"] is False
    assert ev["groundedness"] == 1.0


def test_extractor_and_judge_fallback_modes_logged():
    claims, emode = extract_atomic_claims(
        "The arrested person shall be released on bail promptly. "
        "The magistrate must record reasons in writing.")
    assert len(claims) == 2 and emode
    ok, jmode = judge_claim_supported("bail xyzzy", ["unrelated text here"])
    assert ok is False and jmode


def test_reports_cover_plain_rag():
    docs, chunks = _seeds()
    rows = [{"qid": "q1", "question": "bail non-bailable offences",
             "gold_doc_ids": ["bnss_2023"],
             "gold_chunk_ids": [next(iter(chunks))],
             "answer_span": "x", "answerable": True}]
    rr = retrieval_report(rows, docs, chunks,
                          systems=("baseline_plain_rag",), top_k=4)
    assert rr["baseline_plain_rag"]["top_k"] == 5
    assert "recall@k" in rr["baseline_plain_rag"]
    by_sys = {"baseline_plain_rag": [
        run_system("baseline_plain_rag", r["question"], docs, chunks)
        for r in rows]}
    rep = groundedness_report(by_sys, rows, docs, chunks)
    g = rep["baseline_plain_rag"]
    for key in ("fabrication_count", "trap_refusal_recall", "latency_ms_mean",
                "groundedness", "citation_resolved_rate"):
        assert key in g, key


def test_retrieve_top5_uses_hybrid():
    docs, chunks = _seeds()
    retrieved, backend = retrieve_top5("bail", chunks)
    assert 0 < len(retrieved) <= 5
    assert backend.startswith(("hybrid", "lexical"))


def test_simulated_live_hallucination_caught(monkeypatch):
    """Live wiring check without a key: a hallucinating free-text LLM must
    be flagged fabrication by the extractor + independent judge path."""
    import eval.plain_rag as pr

    # Core api tests pin LLM_PROVIDER=mock at import; pin live-like env here.
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("JUDGE_MODEL", "gemini-2.5-flash")
    monkeypatch.setitem(pr._LIVE, "pipeline", True)
    monkeypatch.setitem(pr._LIVE, "judge", True)
    monkeypatch.setattr(
        pr, "_pipeline_text",
        lambda prompt, timeout=20: "1. The moon court awarded Rs. 999 crore.\n"
                                   "2. Bail is always denied on Tuesdays.",
    )
    monkeypatch.setattr(
        pr, "_judge_text",
        lambda prompt, timeout=20: "NOT_SUPPORTED",
    )
    docs, chunks = _seeds()
    retrieved = list(chunks.values())[:2]
    text = ("The moon court awarded Rs. 999 crore. [fake_moon_doc] "
            "Bail is always denied on Tuesdays.")
    cits = parse_plain_citations(text, docs, retrieved)
    assert any(not c.resolved for c in cits)  # fake citation kept, unresolved
    ev = evaluate_plain_answer(text, cits, retrieved, docs)
    assert ev["fabrication"] is True
    assert ev["unresolved_citations"] == 1
    assert ev["groundedness"] == 0.0
    assert "live" in ev["extract_mode"] and "live" in ev["judge_mode"]
