"""In-memory Doc/Chunk registry + lexical retrieval.

Deliberately dependency-free (token-overlap scoring) so the hackathon
demo works offline. EMBED_MODEL env is reserved for a future vector swap.
"""

import re
from collections import Counter

from contracts.schemas import Chunk, Doc

_TOKEN = re.compile(r"[a-z0-9]+")

# Common stopwords ignored for scoring so a lone "on"/"the"/"in"
# cannot trigger a hit and defeat the refuse-by-default rule.
STOPWORDS = frozenset(
    "a an and are as at be but by for from has have in is it its of on or that the to was were will with".split()
)


def _tokens(s: str) -> list[str]:
    return _TOKEN.findall(s.lower())


def _content_tokens(s: str) -> list[str]:
    return [t for t in _tokens(s) if t not in STOPWORDS]


class Registry:
    """Holds Docs and Chunks; minimal retrieval over chunk text."""

    def __init__(self) -> None:
        self.docs: dict[str, Doc] = {}
        self.chunks: dict[str, Chunk] = {}

    def register_doc(self, doc: Doc) -> None:
        self.docs[doc.doc_id] = doc

    def add_chunks(self, chunks: list[Chunk]) -> None:
        for c in chunks:
            if c.doc_id not in self.docs:
                raise KeyError(f"unknown doc_id: {c.doc_id}")
            self.chunks[c.chunk_id] = c

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        return self.chunks.get(chunk_id)

    def chunk_map(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        return {cid: self.chunks[cid] for cid in chunk_ids if cid in self.chunks}

    def search(
        self,
        query: str,
        top_k: int = 4,
        min_overlap: int = 2,
        min_coverage: float | None = None,
    ) -> list[Chunk]:
        """Rank chunks by content-token overlap. Stopword-only overlap -> [].

        min_overlap (default 2) is the refusal lever, scaled to query length:
        required = min(min_overlap, #distinct query content-tokens). A genuine
        single-term query ('bail') must match fully; multi-token noise sharing
        one term (e.g. near-gibberish with 'quantum') still retrieves nothing
        instead of grounding an answer on noise.

        min_coverage (None -> MIN_COVERAGE env) is the relevance lever for
        traps sharing 3-4 content words: the fraction of distinct query
        content tokens present in the chunk must reach it. The section-label
        bypass skips both gates (an explicit "Section N" ask).
        """
        if min_coverage is None:
            from generation.config import get_min_coverage

            min_coverage = get_min_coverage()
        qtok = _content_tokens(query)
        if not qtok:
            return []
        required = min(min_overlap, len(set(qtok)))
        qcount = Counter(qtok)
        qdistinct = set(qcount)
        scored: list[tuple[int, str]] = []
        for cid, ch in self.chunks.items():
            ccount = Counter(_content_tokens(ch.text))
            overlap = {t for t in qcount if t in ccount}
            if ch.section_label and ch.section_label.lower() in query.lower():
                pass  # explicit section ask: skip both gates
            elif len(overlap) < required:
                continue
            elif len(overlap) / len(qdistinct) < min_coverage:
                continue
            score = sum(min(qcount[t], ccount[t]) for t in overlap)
            # small bonus for section-label match (e.g. "Section 483")
            if ch.section_label and ch.section_label.lower() in query.lower():
                score += 3
            if score > 0:
                scored.append((score, cid))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [self.chunks[cid] for _, cid in scored[:top_k]]
