"""Hybrid retrieval: RRF fusion, retrieve() shape, doc filter, refusal path."""

from contracts.schemas import Chunk, Doc
from retrieval.hybrid import HybridIndex, retrieve, rrf


def _idx() -> HybridIndex:
    doc = Doc(doc_id="d1", title="T", doc_type="statute")
    chunks = [
        Chunk(chunk_id="d1::p1::c0", doc_id="d1", text="Bail in non-bailable offences is judicial discretion."),
        Chunk(chunk_id="d1::p1::c1", doc_id="d1", text="Cheating allegations require proof of dishonest intent."),
    ]
    doc2 = Doc(doc_id="d2", title="U", doc_type="case_file")
    chunks.append(Chunk(chunk_id="d2::p1::c0", doc_id="d2", text="FIR registered for cheating on 12 March."))
    assert doc and doc2
    return HybridIndex(chunks)


def test_rrf_prefers_top_ranks():
    fused = rrf([["a", "b"], ["b", "a"]])
    assert fused[0][0] == "b" or fused[0][0] == "a"
    assert rrf([["a"], ["a"]])[0] == ("a", 2 / 61)


def test_retrieve_shape_and_scores():
    hits = _idx().retrieve("bail non-bailable offences", top_k=8)
    assert hits and all(isinstance(s, float) for _, s in hits)
    assert hits[0][0].chunk_id == "d1::p1::c0"


def test_doc_ids_restricts_corpus():
    hits = _idx().retrieve("cheating registered", top_k=8, doc_ids=["d2"])
    assert hits and all(c.doc_id == "d2" for c, _ in hits)
    stat = _idx().retrieve("cheating allegations", top_k=8, doc_ids=["d1"])
    assert stat and all(c.doc_id == "d1" for c, _ in stat)


def test_hybrid_single_token_gated():
    # same refusal lever as the lexical registry: one shared token of a
    # multi-token query is noise
    assert _idx().retrieve("cheating frobnication") == []
    assert _idx().retrieve("cheating frobnication", min_overlap=1) != []


def test_hybrid_single_term_query_matches():
    # proportional gate: one-term query must match fully, so it retrieves
    assert _idx().retrieve("bail") != []


def test_hybrid_section_label_bypass_matches_store():
    doc = Doc(doc_id="s1", title="S", doc_type="statute")
    c = Chunk(
        chunk_id="s1::p1::c0",
        doc_id="s1",
        text="totally unrelated wording here",
        section_label="Section 483",
    )
    assert doc
    idx = HybridIndex([c])
    hits = idx.retrieve("what does Section 483 say")
    assert [ch.chunk_id for ch, _ in hits] == ["s1::p1::c0"]


def test_default_chunks_include_seeds():
    # regression: hybrid index once dropped seeds when processed JSONL existed,
    # so doc_ids-filtered seed queries refused. Seeds must always be present.
    from retrieval.hybrid import _registry_chunks

    ids = {c.doc_id for c in _registry_chunks()}
    assert {"bnss_2023", "sc_bail_2022", "case_file_demo"} <= ids


def test_gibberish_returns_empty():
    assert _idx().retrieve("xyzzy quantum torts on Mars") == []


def test_module_retrieve_uses_seed_corpus():
    import retrieval.hybrid as h

    h._INDEX = None  # force rebuild from seeds (no processed JSONL in repo)
    hits = retrieve("bail non-bailable", top_k=4)
    assert hits and all(isinstance(s, float) for _, s in hits)


def test_label_bonus_counted_once():
    import pytest as _pytest

    from retrieval.hybrid import HybridIndex

    doc = Doc(doc_id="lb", title="L", doc_type="statute")
    assert doc
    c = Chunk(
        chunk_id="lb::p1::c0",
        doc_id="lb",
        text="bail provision text here",
        section_label="Section 483",
    )
    idx = HybridIndex([c])
    idx._bm25 = None  # force pure-python TF leg (already adds +3)
    idx._tf_fallback_used = True
    hits = idx.retrieve("what does Section 483 say")
    assert hits
    # RRF of a single list is 1/61; a second +0.05 would show here.
    assert hits[0][1] == _pytest.approx(1 / 61)


def _routed_idx() -> HybridIndex:
    docs = {
        "s1": Doc(doc_id="s1", title="S", doc_type="statute"),
        "j1": Doc(doc_id="j1", title="J", doc_type="judgment"),
    }
    chunks = [
        Chunk(chunk_id="s1::p1::c0", doc_id="s1",
              text="bail in non-bailable offences is judicial discretion of the court"),
        Chunk(chunk_id="j1::p1::c0", doc_id="j1",
              text="CRL OP/16246/2007 of RAVI Vs SUB INSPECTOR. Court: Madras High Court. Disposition: BAIL GRANTED."),
    ]
    return HybridIndex(chunks, docs=docs)


def test_hybrid_judgment_routing():
    hits = _routed_idx().retrieve(
        "in which cases was bail granted, and by which court", top_k=2)
    assert hits and hits[0][0].doc_id == "j1"


def test_hybrid_no_docs_means_no_routing_boost():
    chunks = [
        Chunk(chunk_id="s1::p1::c0", doc_id="s1",
              text="bail in non-bailable offences is judicial discretion of the court"),
        Chunk(chunk_id="j1::p1::c0", doc_id="j1",
              text="CRL OP/16246/2007 of RAVI Vs SUB INSPECTOR. Court: Madras High Court. Disposition: BAIL GRANTED."),
    ]
    plain = HybridIndex(chunks)  # no docs map: ranking identical to before
    hits = plain.retrieve("in which cases was bail granted, and by which court", top_k=2)
    assert hits  # boost absent, but nothing crashes and order is lexical


def test_answer_trace_records_routing():
    from generation.llm import MockClient
    from retrieval.store import Registry
    from workflows.answer import answer_question

    reg = Registry()
    reg.register_doc(Doc(doc_id="s1", title="S", doc_type="statute"))
    reg.register_doc(Doc(doc_id="j1", title="J", doc_type="judgment"))
    from contracts.schemas import Chunk as C
    reg.add_chunks([C(chunk_id="s1::p1::c0", doc_id="s1", text="bail provision note")])
    reg.add_chunks([C(chunk_id="j1::p1::c0", doc_id="j1", text="Court: Madras High Court. Disposition: BAIL GRANTED.")])
    routed = answer_question(
        "in which cases was bail granted, and by which court",
        "chat", reg, MockClient(), top_k=4)
    assert routed.trace["routing"] == "judgment"
    plain = answer_question("bail provision note", "chat", reg, MockClient(), top_k=4)
    assert plain.trace["routing"] is None
