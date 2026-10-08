"""Chunk plain text into Chunk models (contracts/schemas.py).

Two APIs:
- chunk_text: legacy fixed-window chunker (kept for seed loading).
- chunk_document: section-aware chunker for ingested files. Statutes split
  on "Section N" headings, judgments on numbered paragraphs, case files by
  page/paragraph. Packing never splits mid-sentence (overlong sentences fall
  back to word-boundary splits).
"""

import re

from contracts.schemas import Chunk, Doc
from ingest.normalize import canonicalize

_SECTION_RE = re.compile(r"(?im)^[ \t]*section\s+(\d+[A-Z]*)\b")
_PARA_RE = re.compile(r"(?m)^\s*(?:\[(\d{1,3})\]|\((\d{1,3})\)|(\d{1,3})[.\)\:-])\s+(?=\S)")
_SENT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"\'(\[])')
_BLANK_LINES = re.compile(r"\n\s*\n")


def chunk_text(
    doc: Doc,
    text: str,
    max_chars: int = 800,
    overlap: int = 100,
    section_label: str | None = None,
    page: int | None = None,
) -> list[Chunk]:
    """Split text into overlapping char windows.

    Each window becomes a Chunk with id "{doc_id}::p{page}::c{n}".
    Paragraph boundaries are preferred but not required.
    """
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    chunks: list[Chunk] = []
    n = 0
    start = 0
    page_no = page if page is not None else 1
    while start < len(cleaned):
        end = min(start + max_chars, len(cleaned))
        if end < len(cleaned):
            cut = cleaned.rfind(". ", start, end)
            if cut > start + max_chars // 3:
                end = cut + 1
        window = cleaned[start:end].strip()
        if window:
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}::p{page_no}::c{n}",
                    doc_id=doc.doc_id,
                    section_label=section_label,
                    page=page_no,
                    text=window,
                )
            )
            n += 1
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def split_statute(text: str) -> list[tuple[str | None, str]]:
    """Split statute text into (section_label, body) on 'Section N' headings."""
    out: list[tuple[str | None, str]] = []
    pos = 0
    current: str | None = None
    for m in _SECTION_RE.finditer(text):
        if m.start() > pos:
            out.append((current, text[pos : m.start()].strip()))
        current = f"Section {m.group(1)}"
        pos = m.end()
    out.append((current, text[pos:].strip()))
    return [(label, body) for label, body in out if body]


def split_judgment(text: str) -> list[tuple[str | None, str]]:
    """Split judgment text into (para_label, body) on numbered paragraphs."""
    out: list[tuple[str | None, str]] = []
    matches = list(_PARA_RE.finditer(text))
    if not matches:
        return [(None, text.strip())] if text.strip() else []
    if matches[0].start() > 0:
        pre = text[: matches[0].start()].strip()
        if pre:
            out.append((None, pre))
    for i, m in enumerate(matches):
        num = m.group(1) or m.group(2) or m.group(3)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end].strip()
        if body:
            out.append((f"Para {num}", body))
    return out


def split_case_file(text: str) -> list[tuple[None, str]]:
    """Split case-file text into (None, paragraph) on blank lines."""
    return [(None, p.strip()) for p in _BLANK_LINES.split(text) if p.strip()]


def split_pages(
    text: str, doc_type: str
) -> list[tuple[str | None, str]]:
    """Dispatch per-page text to the splitter matching doc_type."""
    if doc_type == "statute":
        return split_statute(text)
    if doc_type == "judgment":
        return split_judgment(text)
    return split_case_file(text)


def sentences(text: str) -> list[str]:
    """Split text into sentences (never splits inside a sentence)."""
    return [s.strip() for s in _SENT_RE.split(text) if s.strip()]


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Word-boundary split for a single overlong sentence (last resort)."""
    words, parts, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            parts.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        parts.append(cur)
    return parts or [text]


def chunk_document(
    doc: Doc,
    pages: list[tuple[int, str]],
    doc_type: str,
    max_chars: int = 1200,
) -> list[Chunk]:
    """Section-aware chunking over (page_no, raw_text) pages.

    A new chunk starts on section-label change, page change (case files),
    or when max_chars would be exceeded. Sentence boundaries are always
    respected; section_label and page are preserved per chunk.
    """
    # Flatten to (label, page, sentence), carrying section labels across pages.
    units: list[tuple[str | None, int, str]] = []
    carry: str | None = None
    for page_no, raw in pages:
        text = canonicalize(raw)
        if not text:
            continue
        for label, body in split_pages(text, doc_type):
            if label is not None:
                carry = label
            for sent in sentences(body):
                units.append((carry, page_no, sent))
    # Pack units into chunks.
    chunks: list[Chunk] = []
    n = 0
    cur_label: str | None = None
    cur_page: int | None = None
    cur_sents: list[str] = []
    cur_len = 0

    def flush() -> None:
        nonlocal n, cur_sents, cur_len
        if cur_sents:
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}::p{cur_page}::c{n}",
                    doc_id=doc.doc_id,
                    section_label=cur_label,
                    page=cur_page,
                    text=" ".join(cur_sents),
                )
            )
            n += 1
            cur_sents = []
            cur_len = 0

    for label, page_no, sent in units:
        new_section = label != cur_label and cur_sents
        new_page = (
            doc_type == "case_file" and page_no != cur_page and cur_sents
        )
        too_long = cur_sents and cur_len + 1 + len(sent) > max_chars
        if new_section or new_page or too_long:
            flush()
        if cur_label != label or cur_page != page_no:
            cur_label, cur_page = label, page_no
        for piece in _hard_split(sent, max_chars) if len(sent) > max_chars else [sent]:
            if cur_sents and cur_len + 1 + len(piece) > max_chars:
                flush()
                cur_label, cur_page = label, page_no
            cur_sents.append(piece)
            cur_len += (1 if cur_len else 0) + len(piece)
    flush()
    return chunks
