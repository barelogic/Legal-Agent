"""Court + HF-legal ingest tests (offline fixtures, no S3/HF calls)."""

import io
import json
import tarfile


def _one_page_pdf(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_hf_legal_builder_fixture(tmp_path, monkeypatch):
    import sys

    sys.path.insert(0, ".")
    from corpus import build_corpus as bc

    raw = tmp_path / "raw"
    (raw / "hf_legal").mkdir(parents=True)
    rows = [
        {"id": "Section 1", "text": "This is a sufficiently long statute text span for chunking purposes here.",
         "label": None},
        {"id": "Section 1", "text": "A different long text under the same section id still counts here today.",
         "label": None},
        {"id": "x", "text": "short", "label": None},
    ]
    (raw / "hf_legal" / "lsi_statutes_0000.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    (raw / "hf_legal" / "nope_unknown.jsonl").write_text("{}\n")
    monkeypatch.setitem(bc.HF_LEGAL_FILES, "lsi_statutes_0000",
                        ("statute", "[LSI] ", "https://example.invalid/x"))
    docs, chunks = bc.build_hf_legal_docs(raw)
    assert len(docs) == 2  # short row dropped, unknown file skipped
    assert len({d.doc_id for d in docs}) == 2  # same section id, distinct ids
    assert all(d.source_url == "https://example.invalid/x" for d in docs)
    assert all(c.doc_id in {d.doc_id for d in docs} for c in chunks)
    # stable ids across runs
    docs2, _ = bc.build_hf_legal_docs(raw)
    assert [d.doc_id for d in docs] == [d.doc_id for d in docs2]


def _write_tar(path, members: dict[str, bytes]):
    with tarfile.open(path, "w") as tf:
        for name, data in members.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))


def test_sc_builder_fixture(tmp_path):
    import sys

    sys.path.insert(0, ".")
    from corpus import build_corpus as bc

    yd = tmp_path / "raw" / "sc" / "year=2024"
    yd.mkdir(parents=True)
    pdf = _one_page_pdf("Kumar vs State of Bihar\nIN THE SUPREME COURT OF INDIA")
    _write_tar(yd / "english.tar", {"2024_1_1_2_EN.pdf": pdf})
    meta = json.dumps({"path": "2024_1_1_2", "citation_year": 2024,
                       "nc_display": "2024INSC1"}).encode()
    _write_tar(yd / "metadata.tar", {"2024_1_1_2.json": meta})
    docs, chunks = bc.build_sc_docs(tmp_path / "raw")
    assert len(docs) == 1
    d = docs[0]
    assert d.citation == "2024INSC1" and d.year == 2024
    assert d.source_url.startswith("https://") and "#2024_1_1_2_EN.pdf" in d.source_url
    assert "Kumar" in (d.title or "")
    assert chunks and all(c.doc_id == d.doc_id for c in chunks)


def test_hc_builder_fixture(tmp_path):
    import sys

    sys.path.insert(0, ".")
    from corpus import build_corpus as bc

    bd = tmp_path / "raw" / "hc" / "year=2020" / "court=19_16" / "bench=calcutta_original_side"
    bd.mkdir(parents=True)
    pdf = _one_page_pdf("IN THE HIGH COURT AT CALCUTTA\nOrder dated today")
    _write_tar(bd / "data.tar", {"WBCHCO0010802020_1_2020-09-21.pdf": pdf})
    docs, chunks = bc.build_hc_docs(tmp_path / "raw")
    assert len(docs) == 1
    d = docs[0]
    assert d.year == 2020 and d.doc_type == "judgment"
    assert d.source_url.startswith("https://")
    assert chunks


def test_manifest_origins_and_urls():
    import pathlib

    m = json.loads((pathlib.Path("corpus/manifest.json")).read_text())
    origins = {d.get("origin") for d in m}
    assert {"supreme-court", "high-court", "hf-legal", "synthetic"} <= origins
    for d in m:
        assert d["source_url"] or d["synthetic"], d["doc_id"]
        if d.get("origin") in ("supreme-court", "high-court"):
            assert "#" in d["source_url"], d["doc_id"]
