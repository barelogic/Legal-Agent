"""Build corpus: data/raw/ -> data/processed/{docs,chunks}.jsonl (Doc schema).

- MHA statute PDFs: PyMuPDF extract + section-aware chunking (P1 ingest,
  unmodified). Doc metadata from corpus/sources.py (citation, source_url, year).
- India Code sections: header parsed for source_url/act/section; body chunked
  as one statute section. Citation = "<act name> s.<num>" (verbatim parts only).
- HF bail rows: P1 row_to_doc (doc_id/citation/source_url/year from the row).
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
    builders = (("pdf", False, build_pdf_docs),
                ("section", False, build_section_docs),
                ("hf", False, build_hf_docs),
                ("synthetic", True, build_synthetic_docs))
    all_docs: list[Doc] = []
    all_chunks: list[Chunk] = []
    synthetic_ids: set[str] = set()
    for _name, is_synth, builder in builders:
        try:
            docs, chunks = builder(raw)
        except FileNotFoundError as e:
            print(f"skip ({e}); run fetch scripts first")
            continue
        if is_synth:
            synthetic_ids.update(d.doc_id for d in docs)
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
        "num_chunks": sum(1 for c in all_chunks if c.doc_id == d.doc_id),
    } for d in all_docs]
    (root / "corpus" / "manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"built {len(all_docs)} docs / {len(all_chunks)} chunks -> data/processed/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
