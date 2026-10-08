"""Registry: register/search round-trip."""

from contracts.schemas import Doc
from ingest.chunker import chunk_text
from retrieval.store import Registry


def test_search_finds_bail():
    reg = Registry()
    doc = Doc(doc_id="bnss_2023", title="BNSS", doc_type="statute")
    reg.register_doc(doc)
    reg.add_chunks(chunk_text(doc, "bail in non-bailable offences is judicial discretion"))
    hits = reg.search("bail non-bailable", top_k=2)
    assert hits and hits[0].doc_id == "bnss_2023"


def test_empty_query():
    assert Registry().search("", top_k=2) == []


def _one_token_reg() -> Registry:
    reg = Registry()
    doc = Doc(doc_id="d1", title="T", doc_type="statute")
    reg.register_doc(doc)
    reg.add_chunks(chunk_text(doc, "quantum of punishment is decided by the Court"))
    return reg


def test_single_token_overlap_refused_by_default():
    # near-gibberish sharing one legal term must not retrieve (refusal lever)
    assert _one_token_reg().search("xyzzy quantum frobnication") == []


def test_single_token_overlap_allowed_when_relaxed():
    assert _one_token_reg().search("xyzzy quantum frobnication", min_overlap=1) != []
