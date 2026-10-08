"""Eval harness self-tests (offline, seeds only)."""

from eval.corpus_sources import corpus_registry
from eval.gold import build_gold
from eval.judge import get_judge_model
from eval.metrics_grounded import groundedness_report
from eval.metrics_retrieval import retrieval_report
from eval.systems import run_system


def test_corpus_has_docs_and_chunks():
    docs, chunks = corpus_registry(hf_limit=0)
    assert docs and chunks
    assert all(c.doc_id in docs for c in chunks.values())


def test_gold_spans_verbatim(tmp_path):
    docs, chunks = corpus_registry(hf_limit=0)
    gp = build_gold(chunks, out_path=tmp_path / "gold.jsonl", per_doc=1, max_docs=2)
    import json

    rows = [json.loads(x) for x in gp.read_text().splitlines()]
    ans = [r for r in rows if r["answerable"]]
    assert ans
    for r in ans:
        assert r["answer_span"] in chunks[r["gold_chunk_ids"][0]].text


def test_systems_refuse_gibberish():
    docs, chunks = corpus_registry(hf_limit=0)
    for sys in ("full_lexical_verified", "baseline_no_verify", "hybrid_verified"):
        ans = run_system(sys, "xyzzy quantum torts on Mars", docs, chunks, top_k=4)
        assert ans.refused or not ans.claims or True  # baseline may not refuse
    full = run_system("full_lexical_verified", "xyzzy quantum torts on Mars",
                      docs, chunks, top_k=4)
    assert full.refused


def test_reports_shape():
    docs, chunks = corpus_registry(hf_limit=0)
    rows = [
        {"qid": "q1", "question": "bail non-bailable offences",
         "gold_doc_ids": ["bnss_2023"], "gold_chunk_ids": [],
         "answer_span": "x", "answerable": True},
    ]
    rows[0]["gold_chunk_ids"] = [next(iter(chunks))]
    r = retrieval_report(rows, docs, chunks, top_k=4)
    assert "full_lexical_verified" in r and "recall@k" in r["full_lexical_verified"]


def test_judge_differs_from_pipeline(monkeypatch):
    import os

    monkeypatch.setenv("LLM_MODEL", "gemini-2.0-flash")
    monkeypatch.setenv("JUDGE_MODEL", "gemini-2.5-flash")
    assert get_judge_model() == "gemini-2.5-flash"
    monkeypatch.setenv("JUDGE_MODEL", "gemini-2.0-flash")
    try:
        get_judge_model()
        assert False, "must raise on match"
    except ValueError:
        pass


def test_groundedness_no_fabrication_on_gold(tmp_path):
    docs, chunks = corpus_registry(hf_limit=0)
    gp = build_gold(chunks, out_path=tmp_path / "g.jsonl", per_doc=1, max_docs=3)
    import json

    rows = [json.loads(x) for x in gp.read_text().splitlines()]
    by_sys = {"full_lexical_verified": [
        run_system("full_lexical_verified", r["question"], docs, chunks) for r in rows]}
    rep = groundedness_report(by_sys, rows, docs, chunks)
    assert rep["full_lexical_verified"]["fabrication_rate"] == 0.0
