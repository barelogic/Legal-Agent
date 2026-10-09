"""Ladder tests (mock-pinned, tiny in-memory corpus — no network/LLM)."""

import json
import os

os.environ["LLM_PROVIDER"] = "mock"

import sys

sys.path.insert(0, ".")

from contracts.schemas import Chunk, Doc
from eval.ladder import (STEPS, ladder_retrieval, run_plain_step,
                         run_struct_step, write_compare_jsonl)
from eval.systems import make_registry
from generation.llm import make_client


def _mini():
    docs = {
        "d1": Doc(doc_id="d1", title="Bail Statute", doc_type="statute",
                  citation="BNSS s.478", source_url="https://example.invalid/s478"),
        "d2": Doc(doc_id="d2", title="Remand Note", doc_type="judgment",
                  source_url="https://example.invalid/remand"),
    }
    chunks = {
        "d1::p1::c1": Chunk(chunk_id="d1::p1::c1", doc_id="d1",
                            section_label="Section 478",
                            text="Such person shall be released on bail under section 478 of the BNSS."),
        "d1::p1::c2": Chunk(chunk_id="d1::p1::c2", doc_id="d1",
                            text="The bond amount for appearance shall be fixed by the court."),
        "d2::p1::c1": Chunk(chunk_id="d2::p1::c1", doc_id="d2",
                            text="The accused was produced before the magistrate and remanded."),
    }
    return docs, chunks


def _rows():
    return [
        {"qid": "t1", "question": "When shall such person be released on bail?",
         "answer_span": "shall be released on bail", "answerable": True,
         "trap": False, "holdout": False,
         "gold_chunk_ids": ["d1::p1::c1"], "workflow": "chat"},
        {"qid": "t2", "question": "zxqv wugbench florpnik quantum",
         "answer_span": "", "answerable": False, "trap": True,
         "holdout": False, "gold_chunk_ids": [], "workflow": "chat"},
    ]


def test_all_steps_run_mock():
    docs, chunks = _mini()
    reg = make_registry(docs, chunks)
    from retrieval.hybrid import HybridIndex

    hidx = HybridIndex(list(chunks.values()))
    llm = make_client()
    rows = _rows()
    for s in STEPS:
        for r in rows:
            if s["kind"] == "plain":
                ans = run_plain_step(s, r["question"], docs, chunks, reg, hidx, 4)
                assert ans.trace.get("plain_rag_eval") is not None
            else:
                ans = run_struct_step(s, r["question"], docs, chunks, reg,
                                      hidx, llm, 4)
            assert ans.trace.get("ladder_step") == s["id"]
    # L4 renders without verification; L5+ carry verify flags
    l4 = run_struct_step(STEPS[4], rows[0]["question"], docs, chunks, reg,
                         hidx, llm, 4)
    assert l4.trace.get("unverified") is True
    l5 = run_struct_step(STEPS[5], rows[0]["question"], docs, chunks, reg,
                         hidx, llm, 4)
    assert l5.trace["verify_flags"]["verify_text"] is False


def test_ladder_retrieval_uses_trace():
    docs, chunks = _mini()
    reg = make_registry(docs, chunks)
    from retrieval.hybrid import HybridIndex

    hidx = HybridIndex(list(chunks.values()))
    rows = _rows()
    ans = run_plain_step(STEPS[0], rows[0]["question"], docs, chunks, reg,
                         hidx, 4)
    rep = ladder_retrieval(rows, {"L0_plain_lexical": [ans, ans]})
    assert rep["L0_plain_lexical"]["n"] == 1
    assert 0.0 <= rep["L0_plain_lexical"]["recall@k"] <= 1.0


def test_compare_jsonl_schema(tmp_path):
    docs, chunks = _mini()
    reg = make_registry(docs, chunks)
    from retrieval.hybrid import HybridIndex

    hidx = HybridIndex(list(chunks.values()))
    llm = make_client()
    rows = _rows()
    ours = [run_struct_step(STEPS[8], r["question"], docs, chunks, reg, hidx,
                            llm, 4) for r in rows]
    base = [run_plain_step(STEPS[1], r["question"], docs, chunks, reg, hidx, 4)
            for r in rows]
    p = tmp_path / "compare.jsonl"
    assert write_compare_jsonl(rows, ours, base, docs, chunks, p) == 2
    lines = [json.loads(x) for x in p.read_text().splitlines()]
    for ln in lines:
        assert set(ln) >= {"qid", "question", "answerable", "trap", "ours",
                           "baseline", "delta"}
        assert set(ln["baseline"]) >= {"unsupported_claims", "atomic_claims",
                                       "supported", "text", "refused"}
