"""File ingest pipeline: path -> (Doc, chunks) + JSONL persistence.

Source of truth for ingested files is data/processed/docs.jsonl and
data/processed/chunks.jsonl (one model per line). Saves upsert by doc_id.
"""

import re
from pathlib import Path

from contracts.schemas import Chunk, Doc
from ingest.chunker import chunk_document
from ingest.pdf import extract_pages, read_text_file

DOC_TYPES = ("statute", "judgment", "case_file")
SUFFIXES = (".pdf", ".txt")


def repo_root() -> Path:
    """Repo root (this file is <root>/ingest/pipeline.py)."""
    return Path(__file__).resolve().parent.parent


def processed_dir(base: Path | str | None = None) -> Path:
    """data/processed under base (default: repo root). Created on save."""
    root = Path(base) if base is not None else repo_root()
    return root / "data" / "processed"


def slugify(name: str) -> str:
    """Filename stem -> stable doc_id slug (lowercase, _ separated)."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "doc"


def ingest_file(
    path: str | Path, doc_type: str, base: Path | str | None = None
) -> tuple[Doc, list[Chunk]]:
    """Parse path into a Doc + section-aware Chunks; persists to JSONL.

    Never invents metadata: title comes from the filename, citation stays
    None (canonical citations are resolved from the registry, not recalled).
    base overrides the processed-data root (tests pass a tmp dir).
    """
    if doc_type not in DOC_TYPES:
        raise ValueError(f"doc_type must be one of {DOC_TYPES}")
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"no such file: {src}")
    if src.suffix.lower() not in SUFFIXES:
        raise ValueError(f"unsupported suffix {src.suffix!r}; expected {SUFFIXES}")
    pages = extract_pages(src) if src.suffix.lower() == ".pdf" else read_text_file(src)
    if not any(t.strip() for _, t in pages):
        raise ValueError(f"no extractable text in {src}")
    doc_id = slugify(src.stem)
    doc = Doc(
        doc_id=doc_id,
        title=src.stem.replace("_", " ").replace("-", " "),
        doc_type=doc_type,  # type: ignore[arg-type]
    )
    chunks = chunk_document(doc, pages, doc_type)
    save_processed(doc, chunks, base=base)
    return doc, chunks


def save_processed(
    doc: Doc, chunks: list[Chunk], base: Path | str | None = None
) -> None:
    """Upsert doc + chunks into docs.jsonl / chunks.jsonl by doc_id."""
    save_all([doc], chunks, base=base)


def save_all(
    docs: list[Doc], chunks: list[Chunk], base: Path | str | None = None
) -> None:
    """Merge many docs/chunks into the JSONL store (new doc_ids win)."""
    d = processed_dir(base)
    d.mkdir(parents=True, exist_ok=True)
    new_ids = {x.doc_id for x in docs}
    merged_docs = {x.doc_id: x for x in load_docs(base)}
    for x in docs:
        merged_docs[x.doc_id] = x
    merged_chunks = [c for c in load_chunks(base) if c.doc_id not in new_ids]
    merged_chunks.extend(chunks)
    (d / "docs.jsonl").write_text(
        "".join(x.model_dump_json() + "\n" for x in merged_docs.values()),
        encoding="utf-8",
    )
    (d / "chunks.jsonl").write_text(
        "".join(x.model_dump_json() + "\n" for x in merged_chunks), encoding="utf-8"
    )


def load_docs(base: Path | str | None = None) -> list[Doc]:
    """Read docs.jsonl ([] when absent or a line is corrupt)."""
    path = processed_dir(base) / "docs.jsonl"
    if not path.is_file():
        return []
    out: list[Doc] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(Doc.model_validate_json(line))
            except Exception:
                continue
    return out


def load_chunks(base: Path | str | None = None) -> list[Chunk]:
    """Read chunks.jsonl ([] when absent or a line is corrupt)."""
    path = processed_dir(base) / "chunks.jsonl"
    if not path.is_file():
        return []
    out: list[Chunk] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(Chunk.model_validate_json(line))
            except Exception:
                continue
    return out
