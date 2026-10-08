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
