"""Build corpus: data/raw/ -> data/processed/{docs,chunks}.jsonl (Doc schema).

- MHA statute PDFs: PyMuPDF extract + section-aware chunking (P1 ingest,
  unmodified). Doc metadata from corpus/sources.py (citation, source_url, year).
- India Code sections: header parsed for source_url/act/section; body chunked
  as one statute section. Citation = "<act name> s.<num>" (verbatim parts only).
- HF bail rows: P1 row_to_doc (doc_id/citation/source_url/year from the row).
- HF legal sets (data/raw/hf_legal/*.jsonl): lsi statutes -> statute Docs,
  case texts (lsi dev/test, bail, sujant) -> judgment Docs; source_url is the
  HF blob URL of the originating parquet file. Indian-Law QA pairs are
  derived, not primary law: only built with --with-qa, labelled [QA-DERIVED].
- SC/HC court tars (data/raw/sc|hc/, gitignored): PDFs streamed from the
  year/bench tar + per-file metadata; title = PDF first line or neutral
  citation; source_url = tar object URL + #member fragment (documented in
  corpus/README.md).
- Synthetic case files: doc_type case_file, title prefixed [SYNTHETIC],
  source_url None (manifest flags synthetic:true).
- Merges via save_all (new doc_ids win; P1 seed/processed docs untouched).
- Writes corpus/manifest.json (committed): every doc + source_url + licence.

Re-run: .venv/bin/python corpus/build_corpus.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contracts.schemas import Chunk, Doc
from ingest.chunker import chunk_document
from ingest.pdf import extract_pages

PDF_META = {
    "the_bharatiya_nyaya_sanhita_2023": (
        "The Bharatiya Nyaya Sanhita, 2023", "BNS, 2023", 2023,
        "https://www.mha.gov.in/sites/default/files/2024-04/250883_english_01042024.pdf"),
    "the_bharatiya_sakshya_adhiniyam_2023": (
        "The Bharatiya Sakshya Adhiniyam, 2023", "BSA, 2023", 2023,
        "https://www.mha.gov.in/sites/default/files/2024-04/250882_english_01042024_0.pdf"),
    "the_bharatiya_nagarik_suraksha_sanhita_2023": (
        "The Bharatiya Nagarik Suraksha Sanhita, 2023", "BNSS, 2023", 2023,
        "https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf"),
}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "doc"


def build_pdf_docs(raw: Path) -> tuple[list[Doc], list[Chunk]]:
    """Ingest MHA PDFs from data/raw/statutes/."""
    from ingest.normalize import canonicalize  # noqa: F401 (keeps parity with P1 path)

    docs: list[Doc] = []
    chunks: list[Chunk] = []
    for pdf in sorted((raw / "statutes").glob("*.pdf")):
        meta = PDF_META.get(pdf.stem)
        if meta is None:
            print(f"skip pdf (unknown provenance): {pdf.name}")
            continue
        title, citation, year, url = meta
        doc = Doc(doc_id=f"statute_{_slug(citation.replace(',', ''))}",
                  title=title, doc_type="statute",
                  citation=citation, source_url=url, year=year)
        pages = extract_pages(pdf)
        chs = chunk_document(doc, pages, "statute")
        if not chs:
            print(f"WARNING: no chunks from {pdf.name} (scanned? OCR missing?)")
            continue
        docs.append(doc)
        chunks.extend(chs)
        print(f"pdf: {doc.doc_id} {len(chs)} chunks")
    return docs, chunks


def parse_section_file(p: Path) -> tuple[dict, str]:
    """Parse provenance header + body of an India Code section .txt."""
    lines = p.read_text(encoding="utf-8").splitlines()
    head = {"source_url": "", "act": "", "section": "", "title": ""}
    label_map = {"Source": "source_url", "Act": "act",
                 "Section": "section", "Title": "title"}
    body_start = 0
    for i, ln in enumerate(lines[:8]):
        for label, key in label_map.items():
            if ln.startswith(f"{label}:"):
                head[key] = ln.split(":", 1)[1].strip()
        if ln.startswith("(Text below"):
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:]).strip()
    return head, body


def build_section_docs(raw: Path) -> tuple[list[Doc], list[Chunk]]:
    """Ingest India Code section .txt files."""
    docs: list[Doc] = []
    chunks: list[Chunk] = []
    for p in sorted((raw / "india_code").glob("*.txt")):
        head, body = parse_section_file(p)
        if not body or not head["section"]:
            print(f"skip section file (empty): {p.name}")
            continue
        year_m = re.search(r"(1[789]\d{2}|20\d{2})", head["act"])
        doc = Doc(
            doc_id=f"ic_{_slug(head['act'])[:32]}_s{head['section']}",
            title=f"{head['act']} - Section {head['section']}",
            doc_type="statute",
            citation=f"{head['act']} s.{head['section']}",
            source_url=head["source_url"] or None,
            year=int(year_m.group(1)) if year_m else None,
        )
        chs = chunk_document(doc, [(1, body)], "statute")
        docs.append(doc)
        chunks.extend(chs)
    print(f"sections: {len(docs)} docs")
    return docs, chunks


def build_hf_docs(raw: Path) -> tuple[list[Doc], list[Chunk]]:
    """Ingest saved HF bail rows via P1 row_to_doc."""
    from ingest.hf_cases import row_to_doc

    docs: list[Doc] = []
    chunks: list[Chunk] = []
    for p in sorted((raw / "hf_bail").glob("*.json")):
        row = json.loads(p.read_text(encoding="utf-8"))
        try:
            doc, chs = row_to_doc(row)
        except Exception as e:
            print(f"skip hf row {p.name}: {e}")
            continue
        docs.append(doc)
        chunks.extend(chs)
    print(f"hf judgments: {len(docs)} docs")
    return docs, chunks


HF_LEGAL_FILES = {  # jsonl stem -> (doc_type, title prefix, blob url)
    "sujant": ("judgment", "",
               "https://huggingface.co/datasets/sujantkumarkv/indian_legal_corpus"),
    "lsi_statutes_0000": ("statute", "[LSI] ",
        "https://huggingface.co/datasets/shounakpaul95/Benchmark-Testing/blob/refs/convert/parquet/lsi/statutes/0000.parquet"),
    "lsi_dev_0000": ("judgment", "[LSI] ",
        "https://huggingface.co/datasets/shounakpaul95/Benchmark-Testing/blob/refs/convert/parquet/lsi/dev/0000.parquet"),
    "lsi_test_0000": ("judgment", "[LSI] ",
        "https://huggingface.co/datasets/shounakpaul95/Benchmark-Testing/blob/refs/convert/parquet/lsi/test/0000.parquet"),
    "bail_test_all_0000": ("judgment", "[Bail] ",
        "https://huggingface.co/datasets/shounakpaul95/Benchmark-Testing/blob/refs/convert/parquet/bail/test_all/0000.parquet"),
    "indian_law_qa": ("judgment", "[QA-DERIVED] ",
        "https://huggingface.co/datasets/vishnun0027/Indian-Law/blob/main/data/train-00000-of-00001.parquet"),
}


def build_hf_legal_docs(raw: Path) -> tuple[list[Doc], list[Chunk]]:
    """Ingest normalized HF legal rows (one Doc per row)."""
    docs: list[Doc] = []
    chunks: list[Chunk] = []
    for p in sorted((raw / "hf_legal").glob("*.jsonl")):
        meta = HF_LEGAL_FILES.get(p.stem)
        if meta is None:
            print(f"skip hf_legal (unknown provenance): {p.name}")
            continue
        dtype, prefix, url = meta
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = (row.get("text") or "").strip()
            if len(text) < 40:
                continue
            rid = re.sub(r"[^a-z0-9]+", "_", str(row.get("id", ""))).strip("_")[:40]
            if not rid:
                import hashlib
                rid = hashlib.sha1(text.encode()).hexdigest()[:12]
            doc = Doc(doc_id=f"hfl_{p.stem}_{n:05d}_{rid}",
                      title=f"{prefix}{str(row.get('id', ''))[:80] or p.stem}",
                      doc_type=dtype,  # type: ignore[arg-type]
                      citation=None, source_url=url, year=None)
            chs = chunk_document(doc, [(1, text)], dtype)
            docs.append(doc)
            chunks.extend(chs)
    print(f"hf_legal: {len(docs)} docs")
    return docs, chunks


def _pdf_title(pages: list[tuple[int, str]], fallback: str) -> str:
    for _, text in pages[:2]:
        for line in text.splitlines():
            s = " ".join(line.split())
            if len(s) >= 12 and not s.startswith("<"):
                return s[:160]
    return fallback


def _tar_members(tar_path: Path, suffix: str) -> list[str]:
    import tarfile

    with tarfile.open(tar_path) as tf:
        return [m.name for m in tf.getmembers()
                if m.isfile() and m.name.endswith(suffix)]


def build_sc_docs(raw: Path) -> tuple[list[Doc], list[Chunk]]:
    """Ingest SC year tars: PDFs + neutral citations from metadata.tar."""
    import tarfile

    docs: list[Doc] = []
    chunks: list[Chunk] = []
    for year_d in sorted((raw / "sc").glob("year=*")):
        tar_p, meta_p = year_d / "english.tar", year_d / "metadata.tar"
        if not tar_p.is_file():
            continue
        tar_url = (f"https://indian-supreme-court-judgments.s3.amazonaws.com/"
                   f"data/tar/year={year_d.name.split('=')[1]}/english/english.tar")
        meta: dict[str, dict] = {}
        if meta_p.is_file():
            with tarfile.open(meta_p) as tf:
                for m in tf.getmembers():
                    if m.isfile() and m.name.endswith(".json"):
                        try:
                            rec = json.loads(tf.extractfile(m).read())  # type: ignore[union-attr]
                            meta[m.name[:-5]] = rec
                        except Exception:
                            continue
        pdf_d = year_d / "pdfs"
        pdf_d.mkdir(exist_ok=True)
        with tarfile.open(tar_p) as tf:
            members = [m for m in tf.getmembers()
                       if m.isfile() and m.name.endswith(".pdf")]
            for m in members:
                dest = pdf_d / Path(m.name).name
                if not dest.is_file():
                    with open(dest, "wb") as f:
                        f.write(tf.extractfile(m).read())  # type: ignore[union-attr]
                try:
                    pages = extract_pages(dest)
                except Exception as e:
                    print(f"skip sc pdf {dest.name}: {e}")
                    continue
                if not any(t.strip() for _, t in pages):
                    continue
                stem = dest.stem
                # PDF members carry an _EN suffix the metadata files lack.
                rec = meta.get(stem, {}) or meta.get(re.sub(r"_en$", "", stem, flags=re.I), {})
                nc = rec.get("nc_display") or stem
                year = rec.get("citation_year")
                doc = Doc(doc_id=f"sc_{_slug(stem)}",
                          title=_pdf_title(pages, nc),
                          doc_type="judgment", citation=nc,
                          source_url=f"{tar_url}#{Path(m.name).name}",
                          year=int(year) if year else None)
                chs = chunk_document(doc, pages, "judgment")
                docs.append(doc)
                chunks.extend(chs)
        print(f"sc {year_d.name}: {len(docs)} docs")
    return docs, chunks


def build_hc_docs(raw: Path) -> tuple[list[Doc], list[Chunk]]:
    """Ingest HC bench tars (CNR-ish filenames carry court + date)."""
    import tarfile

    docs: list[Doc] = []
    chunks: list[Chunk] = []
    for tar_p in sorted((raw / "hc").glob("**/data.tar")):
        rel = tar_p.parent.relative_to(raw / "hc")
        parts = rel.parts  # (year=N, court=N_M, bench=NAME)
        info = {p.split("=", 1)[0]: p.split("=", 1)[1] for p in parts
                if "=" in p}
        base = (f"https://indian-high-court-judgments.s3.amazonaws.com/"
                f"data/tar/{rel.as_posix()}/data.tar")
        pdf_d = tar_p.parent / "pdfs"
        pdf_d.mkdir(exist_ok=True)
        with tarfile.open(tar_p) as tf:
            members = [m for m in tf.getmembers()
                       if m.isfile() and m.name.endswith(".pdf")]
            for m in members:
                dest = pdf_d / Path(m.name).name
                if not dest.is_file():
                    with open(dest, "wb") as f:
                        f.write(tf.extractfile(m).read())  # type: ignore[union-attr]
                try:
                    pages = extract_pages(dest)
                except Exception as e:
                    print(f"skip hc pdf {dest.name}: {e}")
                    continue
                if not any(t.strip() for _, t in pages):
                    continue
                stem = dest.stem
                ym = re.search(r"_(\d{4})-(\d{2})-(\d{2})$", stem)
                doc = Doc(
                    doc_id=f"hc_{_slug(info.get('court', 'c'))}_{_slug(stem)[:48]}",
                    title=f"{info.get('court', '')} {info.get('bench', '')} {stem}"[:160],
                    doc_type="judgment", citation=None,
                    source_url=f"{base}#{Path(m.name).name}",
                    year=int(ym.group(1)) if ym else (
                        int(info.get("year", "0").split("=")[-1])
                        if str(info.get("year", "")).isdigit() else None))
                chs = chunk_document(doc, pages, "judgment")
                docs.append(doc)
                chunks.extend(chs)
        print(f"hc {rel}: tar done")
    print(f"hc: {len(docs)} docs")
    return docs, chunks


def build_synthetic_docs(raw: Path) -> tuple[list[Doc], list[Chunk]]:
    """Ingest synthetic case files (labelled in title + banner)."""
    docs: list[Doc] = []
    chunks: list[Chunk] = []
    for p in sorted((raw / "synthetic").glob("*.txt")):
        text = p.read_text(encoding="utf-8")
        assert text.startswith("SYNTHETIC CASE FILE"), f"missing banner: {p.name}"
        doc = Doc(doc_id=_slug(p.stem), title=f"[SYNTHETIC] {p.stem}",
                  doc_type="case_file")
        chs = chunk_document(doc, [(1, text)], "case_file")
        docs.append(doc)
        chunks.extend(chs)
    print(f"synthetic: {len(docs)} docs")
    return docs, chunks


def main(argv: list[str] | None = None) -> int:
    from ingest.pipeline import save_all

    root = Path(__file__).resolve().parent.parent
    raw = root / "data" / "raw"
    builders = (("pdf", False, "mha-pdf", build_pdf_docs),
                ("section", False, "india-code", build_section_docs),
                ("hf", False, "hf-bail", build_hf_docs),
                ("hf_legal", False, "hf-legal", build_hf_legal_docs),
                ("sc", False, "supreme-court", build_sc_docs),
                ("hc", False, "high-court", build_hc_docs),
                ("synthetic", True, "synthetic", build_synthetic_docs))
    all_docs: list[Doc] = []
    all_chunks: list[Chunk] = []
    synthetic_ids: set[str] = set()
    origin_of: dict[str, str] = {}
    for _name, is_synth, origin, builder in builders:
        try:
            docs, chunks = builder(raw)
        except FileNotFoundError as e:
            print(f"skip ({e}); run fetch scripts first")
            continue
        if is_synth:
            synthetic_ids.update(d.doc_id for d in docs)
        for d in docs:
            origin_of.setdefault(d.doc_id, origin)
        all_docs.extend(docs)
        all_chunks.extend(chunks)
    if not all_docs:
        print("no docs built; run corpus/fetch_*.py + make_case_files.py first")
        return 2
    save_all(all_docs, all_chunks)
    manifest = [{
        "doc_id": d.doc_id, "title": d.title, "doc_type": d.doc_type,
        "citation": d.citation, "source_url": d.source_url, "year": d.year,
        # Provenance tracked from the builder above, never inferred from
        # the doc_id slug (slugs are allowed to change).
        "synthetic": d.doc_id in synthetic_ids,
        "origin": origin_of.get(d.doc_id, "?"),
        "num_chunks": sum(1 for c in all_chunks if c.doc_id == d.doc_id),
    } for d in all_docs]
    (root / "corpus" / "manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"built {len(all_docs)} docs / {len(all_chunks)} chunks -> data/processed/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
