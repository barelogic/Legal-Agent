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


def test_section_heading_kept_in_body():
    from ingest.chunker import split_statute

    parts = split_statute("Preamble words.\nSection 483 Bail text here.\nSection 484 Other text.")
    assert parts[1][0] == "Section 483"
    assert "Section 483" in parts[1][1]
    assert "Section 484" in parts[2][1]
