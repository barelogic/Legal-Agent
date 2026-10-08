"""Chunker: ids stable, text preserved, empty -> []."""

from contracts.schemas import Doc
from ingest.chunker import chunk_text


def _doc() -> Doc:
    return Doc(doc_id="d1", title="T", doc_type="statute")


def test_basic_chunk():
    cs = chunk_text(_doc(), "Hello world. " * 50, max_chars=100, overlap=10)
    assert len(cs) >= 2
    assert all(c.chunk_id.startswith("d1::p1::c") for c in cs)
    assert all(c.text for c in cs)


def test_empty():
    assert chunk_text(_doc(), "   ") == []
