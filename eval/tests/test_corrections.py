"""Corrections sweep regression tests (eval-owned, offline)."""

import json

from contracts.schemas import Chunk, Doc


def test_gold_span_floor_extends_stubs():
    from eval.gold import answer_span_for

    c = Chunk(chunk_id="d::p1::c0", doc_id="d", text="No. Complex. The full rule follows hereafter.")
    span = answer_span_for(c)
    assert span in c.text
    from eval.gold import _content_tokens

    assert len(_content_tokens(span)) >= 4


def test_judge_overlap_is_symmetric():
    from eval.judge import _overlap

    # Short gold inside a rambling answer must NOT score 1.0.
    assert _overlap("released on bail", "released on bail " + "filler " * 50) < 1.0
    assert _overlap("released on bail", "released on bail") == 1.0
    assert _overlap("", "anything") == 0.0


def test_judge_no_self_grade_without_span():
    from eval.judge import judge_answers
    from eval.systems import run_system
    from eval.corpus_sources import corpus_registry

    docs, chunks = corpus_registry(hf_limit=0)
    rows = [{"qid": "q1", "question": "bail", "gold_doc_ids": [],
             "gold_chunk_ids": [], "answer_span": "", "answerable": True}]
    by_sys = {"full_lexical_verified": [
        run_system("full_lexical_verified", "bail", docs, chunks)]}
    out = judge_answers(by_sys, rows)
    assert out["full_lexical_verified"]["entailment_rate"] == 0.0


def test_workflow_passthrough():
    from eval.corpus_sources import corpus_registry
    from eval.systems import run_system

    docs, chunks = corpus_registry(hf_limit=0)
    ans = run_system("full_lexical_verified", "bail", docs, chunks,
                     workflow="review")
    assert ans.workflow == "review"


def test_score_queries_graceful_skip():
    from eval.score_queries import score_queries, try_load_processed_corpus

    out = score_queries({}, {})
    assert out["skipped"]
    docs, chunks = try_load_processed_corpus()
    assert isinstance(docs, dict) and isinstance(chunks, dict)


def test_dense_available_no_privates():
    from eval.plain_rag import dense_available, retrieve_top5
    from eval.corpus_sources import corpus_registry

    assert dense_available() is False  # tfidf-local here; libs absent
    docs, chunks = corpus_registry(hf_limit=0)
    retrieved, backend = retrieve_top5("bail", chunks)
    assert backend == "hybrid-bm25"
    assert retrieved


def test_section_map_no_extraction_join():
    import pathlib

    m = json.loads((pathlib.Path("corpus/section_map.json")).read_text())
    for r in m["rows"]:
        assert "herebyrepealed" not in r["quote"]
    assert all("quote_normalized" in r for r in m["rows"])


def test_manifest_synthetic_provenance():
    import pathlib

    m = json.loads((pathlib.Path("corpus/manifest.json")).read_text())
    by_id = {d["doc_id"]: d for d in m}
    synth = [d for d in m if d["synthetic"]]
    assert synth, "no synthetic docs flagged"
    assert all(d["source_url"] or d["synthetic"] for d in m)


def test_doc_ids_path_on_processed():
    from retrieval.hybrid import HybridIndex

    from eval.score_queries import try_load_processed_corpus

    docs, chunks = try_load_processed_corpus()
    if not chunks:
        return  # seeds-only env: covered by test_short_queries instead
    idx = HybridIndex(list(chunks.values()))
    hits = idx.retrieve("bail", top_k=4, doc_ids=["statute_bnss_2023"])
    assert hits and all(c.doc_id == "statute_bnss_2023" for c, _ in hits)


def test_groundedness_reports_trap_def():
    from eval.corpus_sources import corpus_registry
    from eval.metrics_grounded import groundedness_report
    from eval.systems import run_system

    docs, chunks = corpus_registry(hf_limit=0)
    rows = [{"qid": "q1", "question": "bail", "gold_doc_ids": [],
             "gold_chunk_ids": [next(iter(chunks))],
             "answer_span": "x", "answerable": True,
             "trap": False},
            {"qid": "q2", "question": "xyzzy", "gold_doc_ids": [],
             "gold_chunk_ids": [], "answer_span": "", "answerable": False,
             "trap": True}]
    by_sys = {"full_lexical_verified": [
        run_system("full_lexical_verified", r["question"], docs, chunks)
        for r in rows]}
    g = groundedness_report(by_sys, rows, docs, chunks)["full_lexical_verified"]
    assert g["trap_def"] == "trap-flag"
    assert g["n_traps"] == 1
    assert "fabrication_count" in g and "latency_ms_mean" in g
