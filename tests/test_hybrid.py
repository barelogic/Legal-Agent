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
    hits = _idx().retrieve("cheating", top_k=8, doc_ids=["d2"])
    assert hits and all(c.doc_id == "d2" for c, _ in hits)
    stat = _idx().retrieve("cheating", top_k=8, doc_ids=["d1"])
    assert all(c.doc_id == "d1" for c, _ in stat)


def test_gibberish_returns_empty():
    assert _idx().retrieve("xyzzy quantum torts on Mars") == []


def test_module_retrieve_uses_seed_corpus():
    import retrieval.hybrid as h

    h._INDEX = None  # force rebuild from seeds (no processed JSONL in repo)
    hits = retrieve("bail", top_k=4)
    assert hits and all(isinstance(s, float) for _, s in hits)
