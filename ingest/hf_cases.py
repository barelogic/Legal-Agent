"""Ingest HuggingFace case-law rows (Sumitedu/indian-case-laws) as judgments.

Each row becomes one Doc (doc_type="judgment") + section-aware Chunks built
from the row's own text fields. No metadata is invented: doc_id comes from
the CNR number, citation from the row's citation/docket fields, year from
decision_year. NOTE: indexable_text is a metadata summary, not the full
judgment — chunks support case-level facts (court, date, disposition).

CLI: python -m ingest.hf_cases --limit 100 --disposition "BAIL GRANTED"
"""

import argparse
import sys
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contracts.schemas import Chunk, Doc  # noqa: E402
from ingest.chunker import chunk_document  # noqa: E402
from ingest.pipeline import save_all, slugify  # noqa: E402

HF_DATASET = "Sumitedu/indian-case-laws"


def row_to_doc(row: dict, fallback: str = "") -> tuple[Doc, list[Chunk]]:
    """Map one HF row to (Doc, chunks). Every field comes from the row.

    fallback disambiguates rows with no CNR and no metadata id (both empty
    slug to "doc" and would collide); ingest_hf passes the row index.
    """
    cnr = (row.get("cnr_number") or "").strip()
    source = (row.get("dataset_source") or "hc").strip() or "hc"
    meta_id = (row.get("case_metadata_id") or "").strip()
    stem = f"{source}_{cnr}" if cnr else meta_id
    if not stem.strip():
        stem = fallback.strip() or "hf_row_unknown"
    doc_id = slugify(stem)
    title = (row.get("case_title") or doc_id).strip()
    citation = (
        row.get("neutral_citation")
        or row.get("law_report_citation")
        or row.get("docket_number")
        or None
    )
    year = row.get("decision_year") or row.get("citation_year")
    try:
        year_int = int(year) if year not in (None, "") else None
    except (ValueError, TypeError):
        year_int = None  # e.g. "unknown": no year invented
    doc = Doc(
        doc_id=doc_id,
        title=title,
        doc_type="judgment",
        citation=citation,
        source_url=row.get("source_pdf_s3_url"),
        year=year_int,
    )
    header_lines = [
        f"Case: {title}.",
        f"Court: {row.get('court_name') or 'unknown'}.",
        f"Decided: {row.get('decision_date') or 'unknown'}.",
        f"Disposition: {row.get('disposition_text') or 'unknown'}.",
        f"Docket: {row.get('docket_number') or 'unknown'}.",
    ]
    body = (row.get("headnote_text") or "").strip()
    indexable = (row.get("indexable_text") or "").strip()
    text = "\n".join(header_lines)
    if body:
        text += f"\nHeadnote: {body}"
    if indexable:
        text += f"\n{indexable}"
    chunks = chunk_document(doc, [(1, text)], "judgment")
    return doc, chunks


def iter_hf_rows(
    limit: int = 100,
    disposition: str | None = None,
    court: str | None = None,
    max_scan: int = 20000,
) -> Iterator[dict]:
    """Stream rows from HF (never loads 17M rows). Filters apply client-side.

    max_scan is a scan budget counting every streamed row INCLUDING
    filter-skipped ones, so a heavily filtered ingest can return fewer than
    `limit` docs. Raise max_scan if a filtered ingest comes up short.
    """
    try:
        from datasets import load_dataset
    except ImportError as e:
        raise RuntimeError("datasets lib not installed (pip install datasets)") from e
    ds = load_dataset(HF_DATASET, split="train", streaming=True)
    kept = 0
    for i, row in enumerate(ds):
        if kept >= limit or i >= max_scan:
            break
        if disposition and (row.get("disposition_text") or "").upper() != disposition.upper():
            continue
        if court and court.lower() not in (row.get("court_name") or "").lower():
            continue
        kept += 1
        yield dict(row)


def ingest_hf(
    limit: int = 100,
    disposition: str | None = None,
    court: str | None = None,
    base: Path | str | None = None,
) -> tuple[list[Doc], list[Chunk]]:
    """Stream, map and persist HF rows. Returns (docs, chunks)."""
    docs: list[Doc] = []
    chunks: list[Chunk] = []
    for n, row in enumerate(
        iter_hf_rows(limit=limit, disposition=disposition, court=court)
    ):
        doc, chs = row_to_doc(row, fallback=f"hf_row_{n}")
        docs.append(doc)
        chunks.extend(chs)
    if docs:
        save_all(docs, chunks, base=base)
    return docs, chunks


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for python -m ingest.hf_cases."""
    ap = argparse.ArgumentParser(description="Ingest HF Indian case laws")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--disposition", default=None, help='e.g. "BAIL GRANTED"')
    ap.add_argument("--court", default=None, help="substring of court_name")
    args = ap.parse_args(argv)
    docs, chunks = ingest_hf(
        limit=args.limit, disposition=args.disposition, court=args.court
    )
    print(f"ingested {len(docs)} docs, {len(chunks)} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
