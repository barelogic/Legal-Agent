"""Corpus builder: real, traceable docs with source_url for every Doc.

Sources (public only):
- Seed demo files in data/*.txt are marked demo=True and carry a
  source_url of None + note. They are NOT real law and are excluded from
  real-law groundedness claims; they exist so the harness runs offline.
- HuggingFace Sumitedu/indian-case-laws rows (the dataset given to user1)
  become judgment Docs. doc_id from CNR, citation from row fields,
  source_url from source_pdf_s3_url. Every field comes from the row.

Official portals (India Code / eSCR) are network-blocked from this
environment (403/timeout), so no statute snapshot is faked. When fetch
works, add rows to STATUTE_SOURCES and re-run; until then the write-up
must state the statute gap honestly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from contracts.schemas import Chunk, Doc
from ingest.chunker import chunk_document
from ingest.seed import load_seeds

HF_DATASET = "Sumitedu/indian-case-laws"

# Statute snapshots to fill when official fetch works. Each entry MUST have
# a resolvable official source_url before its text is checked in.
STATUTE_SOURCES: list[dict] = []


@dataclass
class CorpusStats:
    num_docs: int
    num_chunks: int
    num_real: int  # docs with source_url set
    num_demo: int


def corpus_registry(
    hf_limit: int = 50,
    disposition: str | None = None,
    base: Path | str | None = None,
) -> tuple[dict[str, Doc], dict[str, Chunk]]:
    """Build (docs, chunks) from seeds + HF sample. Offline-safe.

    Seeds always load. HF streaming failure degrades to seeds only
    (stats record the gap; run_all.py surfaces it in results).
    """
    from ingest.hf_cases import row_to_doc

    root = Path(__file__).resolve().parent.parent
    reg = load_seeds(root / "data")
    docs: dict[str, Doc] = dict(reg.docs)
    chunks: dict[str, Chunk] = dict(reg.chunks)

    if hf_limit > 0:
        try:
            from ingest.hf_cases import iter_hf_rows

            for row in iter_hf_rows(limit=hf_limit, disposition=disposition):
                try:
                    doc, chs = row_to_doc(row)
                except Exception:
                    continue
                if doc.doc_id in docs:
                    continue
                docs[doc.doc_id] = doc
                for c in chs:
                    chunks[c.chunk_id] = c
        except Exception as e:
            print(f"[eval] HF sample skipped ({e}); using seeds only")
    void = base  # reserved: file-backed corpus lives under eval/datasets/
    _ = void
    return docs, chunks


def build_corpus(
    out_dir: Path | str = "eval/datasets",
    hf_limit: int = 50,
    disposition: str | None = None,
) -> CorpusStats:
    """Persist corpus snapshot (docs.jsonl + chunks.jsonl + manifest)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    docs, chunks = corpus_registry(hf_limit=hf_limit, disposition=disposition)
    (out / "corpus_docs.jsonl").write_text(
        "".join(d.model_dump_json() + "\n" for d in docs.values()), encoding="utf-8"
    )
    (out / "corpus_chunks.jsonl").write_text(
        "".join(c.model_dump_json() + "\n" for c in chunks.values()), encoding="utf-8"
    )
    manifest = [
        {
            "doc_id": d.doc_id,
            "title": d.title,
            "doc_type": d.doc_type,
            "citation": d.citation,
            "source_url": d.source_url,
            "year": d.year,
            "demo": d.source_url is None,
        }
        for d in docs.values()
    ]
    (out / "corpus_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    real = sum(1 for d in docs.values() if d.source_url)
    return CorpusStats(len(docs), len(chunks), real, len(docs) - real)


def chunk_document_for_eval(doc: Doc, text: str) -> list[Chunk]:
    """Thin wrapper so ablations can swap chunkers without touching ingest/."""
    return chunk_document(doc, [(1, text)], doc.doc_type)
