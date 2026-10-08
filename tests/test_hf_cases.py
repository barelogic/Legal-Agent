"""HF case-law ingest: row mapping + bulk save (offline, fake rows)."""

from contracts.schemas import Chunk, Doc
from ingest.hf_cases import HF_DATASET, row_to_doc
from ingest.pipeline import load_chunks, load_docs, save_all


def _row(**kw) -> dict:
    base = {
        "case_metadata_id": "case_meta:hc:2020:1:court:CNR123:file_1_2020-01-01",
        "dataset_source": "hc",
        "case_title": "CR. MISC./1/2020 of X Vs State",
        "court_name": "Patna High Court",
        "decision_date": "2020-01-14",
        "decision_year": 2020,
        "disposition_text": "BAIL GRANTED",
        "docket_number": "CR. MISC./1/2020",
        "cnr_number": "CNR123",
        "neutral_citation": None,
        "law_report_citation": None,
        "headnote_text": None,
        "indexable_text": "Case title: X. Bail was granted by the Court.",
        "source_pdf_s3_url": "https://example.invalid/x.pdf",
    }
    base.update(kw)
    return base


def test_dataset_name():
    assert HF_DATASET == "Sumitedu/indian-case-laws"


def test_row_mapping():
    doc, chunks = row_to_doc(_row())
    assert doc.doc_type == "judgment"
    assert doc.doc_id == "hc_cnr123"
    assert doc.citation == "CR. MISC./1/2020"  # falls back to docket, not invented
    assert doc.year == 2020
    assert doc.source_url == "https://example.invalid/x.pdf"
    assert chunks and all(isinstance(c, Chunk) for c in chunks)
    assert all(c.chunk_id.startswith("hc_cnr123::p1::c") for c in chunks)
    assert "BAIL GRANTED" in chunks[0].text  # disposition preserved for retrieval


def test_neutral_citation_preferred():
    doc, _ = row_to_doc(_row(neutral_citation="2020 SCC OnLine Pat 1"))
    assert doc.citation == "2020 SCC OnLine Pat 1"


def test_ingest_rows_bulk_save(tmp_path):
    from ingest.hf_cases import ingest_hf  # noqa: F401  (signature check)
    import ingest.hf_cases as h

    rows = [_row(cnr_number=f"CNR{i}") for i in range(3)]
    docs, chunks = [], []
    for r in rows:
        d, ch = row_to_doc(r)
        docs.append(d)
        chunks.extend(ch)
    save_all(docs, chunks, base=tmp_path)
    assert len(load_docs(base=tmp_path)) == 3
    assert len(load_chunks(base=tmp_path)) == len(chunks)
    assert isinstance(h.HF_DATASET, str) and isinstance(docs[0], Doc)


def test_bad_year_is_none_not_500():
    doc, _ = row_to_doc(_row(decision_year="unknown", citation_year=""))
    assert doc.year is None
    doc, _ = row_to_doc(_row(decision_year="2021"))
    assert doc.year == 2021


def test_empty_ids_do_not_collide():
    a, _ = row_to_doc(_row(cnr_number="", case_metadata_id=""), fallback="hf_row_3")
    b, _ = row_to_doc(_row(cnr_number="", case_metadata_id=""), fallback="hf_row_7")
    assert a.doc_id and b.doc_id and a.doc_id != b.doc_id
