"""Gold dataset: queries with known source references.

Traceability rule: every gold answer span MUST be a verbatim substring
of a gold chunk. Two query kinds:
- answerable: question derived from a real chunk's text; gold_chunk_ids
  point at chunks containing the answer span. Built programmatically
  from the corpus so references cannot drift.
- unanswerable: gibberish/out-of-corpus question; gold expects refusal.
  Any non-refused answer on these is a groundedness failure.

Schema: one JSON object per line:
  {qid, question, gold_doc_ids, gold_chunk_ids, answer_span, answerable}
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from contracts.schemas import Chunk

_TOKEN = re.compile(r"[a-z0-9]+")


def _content_tokens(s: str) -> list[str]:
    stop = {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
        "from", "has", "have", "in", "is", "it", "its", "of", "on", "or",
        "that", "the", "to", "was", "were", "will", "with",
    }
    return [t for t in _TOKEN.findall(s.lower()) if t not in stop]


def derive_question(chunk: Chunk, max_words: int = 8) -> str:
    """Question tokens drawn from the chunk itself (retrievable by design).

    Drops tokens containing digits (dockets/CNRs/dates) so the question
    uses generic legal vocabulary shared across docs. This makes ranking
    non-trivial: many chunks match, the gold must rank highly.
    """
    toks = [t for t in _content_tokens(chunk.text) if not any(ch.isdigit() for ch in t)]
    seen: list[str] = []
    for t in toks:
        if t not in seen:
            seen.append(t)
        if len(seen) >= max_words:
            break
    return " ".join(seen) if seen else chunk.text[:60]


def answer_span_for(chunk: Chunk, max_len: int = 180) -> str:
    """First sentence (or head slice); always a verbatim substring."""
    parts = chunk.text.split(". ")
    first = parts[0].strip()
    if re.search(r"\b[vV]$", first) and len(parts) > 1:
        first = (first + ". " + parts[1]).strip()
    if len(first) > max_len:
        first = first[:max_len].rsplit(" ", 1)[0]
    return first


UNANSWERABLE = [
    "xyzzy quantum torts on Mars",
    "what did the Martian high court hold on lunar bail in 2099?",
    "section 99999 of the fictional moon code procedure?",
]


def build_gold(
    chunks: dict[str, Chunk],
    out_path: Path | str = "eval/datasets/gold.jsonl",
    per_doc: int = 2,
    max_docs: int = 30,
) -> Path:
    """Write gold.jsonl from real chunks. Skips docs with no content tokens."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    by_doc: dict[str, list[Chunk]] = {}
    for c in chunks.values():
        by_doc.setdefault(c.doc_id, []).append(c)
    rows: list[dict] = []
    qid = 0
    for doc_id in sorted(by_doc)[:max_docs]:
        kept = 0
        for c in sorted(by_doc[doc_id], key=lambda x: x.chunk_id):
            if kept >= per_doc:
                break
            q = derive_question(c)
            span = answer_span_for(c)
            if not q or not span or span not in c.text:
                continue
            qid += 1
            rows.append(
                {
                    "qid": f"q{qid:03d}",
                    "question": q,
                    "gold_doc_ids": [doc_id],
                    "gold_chunk_ids": [c.chunk_id],
                    "answer_span": span,
                    "answerable": True,
                }
            )
            kept += 1
    for uq in UNANSWERABLE:
        qid += 1
        rows.append(
            {
                "qid": f"q{qid:03d}",
                "question": uq,
                "gold_doc_ids": [],
                "gold_chunk_ids": [],
                "answer_span": "",
                "answerable": False,
            }
        )
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return out


def load_gold(path: Path | str = "eval/datasets/gold.jsonl") -> list[dict]:
    p = Path(path)
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
