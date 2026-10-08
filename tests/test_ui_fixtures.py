"""Fixture validity: every ui/fixtures/*.json parses and is self-consistent.

Mirrors the backend verifier (quote verbatim in cited chunk), resolves all
chunk_ids/citations against the fixture registry, and pins the loader.
"""

import pytest

from contracts.schemas import Answer
from ui import fixtures as fx
from ui.render import load_template, precheck_summary


def _reg():
    return fx.load_registry()


def test_all_fixtures_parse_as_answers():
    for name in fx.FIXTURE_NAMES:
        ans = fx.load_answer(name)
        assert isinstance(ans, Answer), name
        assert ans.workflow in ("chat", "draft", "review", "research"), name


def test_registry_parses():
    docs, chunks = _reg()
    assert len(docs) == 3 and len(chunks) == 6


def test_verified_quotes_verbatim_in_cited_chunks():
    _, chunks = _reg()
    for name in fx.FIXTURE_NAMES:
        for c in fx.load_answer(name).claims:
            if c.status != "verified":
                continue
            assert c.quote.strip(), (name, c.claim_id)
            assert any(
                c.quote in chunks[cid].text
                for cid in c.chunk_ids
                if cid in chunks
            ), (name, c.claim_id)


def test_all_chunk_ids_and_citations_resolve():
    docs, chunks = _reg()
    doc_ids = {d.doc_id for d in docs}
    for name in fx.FIXTURE_NAMES:
        ans = fx.load_answer(name)
        for c in ans.claims:
            for cid in c.chunk_ids:
                assert cid in chunks, (name, cid)
        for cite in ans.citations:
            assert cite.resolved and cite.doc_id in doc_ids, (name, cite)


def test_contradiction_chunks_exist():
    _, chunks = _reg()
    for k in fx.load_answer("review").contradictions:
        assert k.claim_a in chunks and k.claim_b in chunks
        assert chunks[k.claim_a].text != chunks[k.claim_b].text


def test_refusal_shape():
    ans = fx.load_answer("refusal")
    assert ans.refused and ans.text == "Not found in the provided sources"
    assert ans.refusal_reason and ans.confidence is None


def test_precheck_fixture_drives_summary():
    s = precheck_summary(fx.load_answer("precheck"), load_template("bail_application"))
    assert (s["sourced_n"], s["total"]) == (17, 19)
    assert s["unconfirmed"] is False


def test_draft_fixture_seeds_user_value():
    assert fx.demo_provided_values(fx.load_answer("draft")) == {"FIR number": "0123/2024"}
    assert fx.demo_provided_values(fx.load_answer("chat")) == {}


def test_loader_rejects_unknown():
    with pytest.raises(ValueError):
        fx.load_answer("nope")
    with pytest.raises(RuntimeError):
        fx.get_chunk("nope::p0::c0")


def test_every_workflow_has_a_fixture():
    assert set(fx.WORKFLOW_FIXTURE) == {"chat", "draft", "review", "research"}
    assert fx.WORKFLOW_FIXTURE["research"] == "refusal"  # off-corpus demo refuses
    for wf, name in fx.WORKFLOW_FIXTURE.items():
        assert name in fx.FIXTURE_NAMES
        fx.load_answer(name)  # must not raise


def _sample_rows() -> list:
    import json
    from pathlib import Path

    p = Path(__file__).resolve().parent.parent / "ui" / "fixtures" / "compare_sample.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def test_compare_sample_rows_valid_and_labelled():
    rows = _sample_rows()
    assert len(rows) >= 2
    for r in rows:
        assert "hand-built sample" in r["mode"]  # never mistaken for measured eval
        assert r["question"] and r["baseline"]["text"]
        assert r["baseline_unsupported"], r["qid"]  # the point of the screen
        Answer(**r["ours"])  # must render in the ours column
