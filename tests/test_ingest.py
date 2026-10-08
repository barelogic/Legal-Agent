"""Ingest: normalize, section-aware splits, packing, file pipeline."""

from pathlib import Path

from contracts.schemas import Doc
from ingest.chunker import (
    chunk_document,
    sentences,
    split_case_file,
    split_judgment,
    split_statute,
)
from ingest.normalize import canonicalize
from ingest.pipeline import ingest_file, load_chunks, load_docs, slugify


def _doc(doc_id: str = "t1") -> Doc:
    return Doc(doc_id=doc_id, title="T", doc_type="statute")


def test_canonicalize():
    assert canonicalize("  “Bail” —\u00a0rule…  ") == '"Bail" - rule...'
    assert canonicalize("ABC", fold_case=True) == "abc"


def test_slugify():
    assert slugify("BNSS 2023 (final).pdf".rsplit(".", 1)[0]) == "bnss_2023_final"


def test_statute_split_labels():
    secs = split_statute("Preamble words.\nSection 483 Bail matters.\nSection 484 More.")
    assert [label for label, _ in secs] == [None, "Section 483", "Section 484"]


def test_judgment_split_paras():
    paras = split_judgment("Headnote.\n14. Bail is the rule.\n15. Jail is the exception.")
    assert [label for label, _ in paras] == [None, "Para 14", "Para 15"]


def test_case_file_paragraphs():
    assert len(split_case_file("para one.\n\npara two.")) == 2


def test_chunk_document_preserves_labels_and_pages():
    pages = [
        (1, "Section 483 Bail may be granted by the Court. It is discretionary."),
        (2, "Section 484 Bail conditions apply. Presence must be ensured."),
    ]
    chunks = chunk_document(_doc(), pages, "statute", max_chars=500)
    assert chunks
    labels = {c.section_label for c in chunks}
    assert {"Section 483", "Section 484"} <= labels
    by_label = {c.section_label: c for c in chunks}
    assert by_label["Section 483"].page == 1
    assert by_label["Section 484"].page == 2


def test_never_splits_mid_sentence():
    text = "First sentence here. Second sentence here. Third sentence here."
    chunks = chunk_document(_doc(), [(1, text)], "case_file", max_chars=40)
    assert len(chunks) > 1
    for c in chunks:
        joined = " ".join(sentences(c.text))
        assert joined == c.text  # chunk boundaries align with sentence boundaries


def test_ingest_txt_file(tmp_path: Path):
    src = tmp_path / "demo_act.txt"
    src.write_text("Section 1 Short title. This Act applies.\nSection 2 Bail rules apply.")
    doc, chunks = ingest_file(src, "statute", base=tmp_path)
    assert doc.doc_id == "demo_act" and chunks
    assert all(c.doc_id == "demo_act" for c in chunks)


def test_jsonl_roundtrip_and_upsert(tmp_path: Path):
    from ingest.pipeline import save_processed

    doc = _doc("up1")
    src = tmp_path / "up1.txt"
    src.write_text("Section 1 Words here. More words here.")
    _, chunks = ingest_file(src, "statute", base=tmp_path)
    save_processed(doc, chunks, base=tmp_path)
    assert len(load_docs(base=tmp_path)) == 1
    assert len(load_chunks(base=tmp_path)) == len(chunks)
    save_processed(doc, chunks[:1], base=tmp_path)  # re-save replaces, not appends
    assert len(load_chunks(base=tmp_path)) == 1


def test_ingest_bad_doctype(tmp_path: Path):
    src = tmp_path / "x.txt"
    src.write_text("hi")
    try:
        ingest_file(src, "blog", base=tmp_path)
        assert False
    except ValueError:
        assert True


def test_ingest_pdf(tmp_path: Path):
    fitz = __import__("fitz")
    pdf = tmp_path / "sample_act.pdf"
    d = fitz.open()
    page = d.new_page()
    page.insert_text((72, 72), "Section 5 Bail may be granted. Conditions apply.")
    d.save(pdf)
    d.close()
    doc, chunks = ingest_file(pdf, "statute", base=tmp_path)
    assert doc.doc_id == "sample_act"
    assert any(c.section_label == "Section 5" for c in chunks)
