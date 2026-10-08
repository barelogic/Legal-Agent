"""Hybrid retrieval: BM25 + dense (Chroma) fused by RRF, cross-encoder rerank.

Heavy deps (rank_bm25, chromadb, sentence-transformers) are optional and
lazy: when missing — or models can't download offline — retrieval degrades
to lexical scoring so the pipeline keeps working end-to-end. Embeddings
persist in CHROMA_DIR, so they are computed once and cached on disk.
"""

import os
import re
from pathlib import Path

from contracts.schemas import Chunk

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an and are as at be but by for from has have in is it its of on or that the to was were will with".split()
)

RRF_K = 60


def get_retrieval_backend() -> str:
    """lexical (default) or hybrid. Hybrid falls back to lexical when ML is absent."""
    return os.getenv("RETRIEVAL_BACKEND", "lexical").strip().lower() or "lexical"


def get_embed_model() -> str:
    return os.getenv("EMBED_MODEL", "BAAI/bge-m3").strip() or "BAAI/bge-m3"


def get_reranker_model() -> str:
    return os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base").strip()


def get_chroma_dir() -> Path:
    root = Path(__file__).resolve().parent.parent
    return Path(os.getenv("CHROMA_DIR", str(root / "data" / "chroma")))


def _tokens(s: str) -> list[str]:
    return [t for t in _TOKEN.findall(s.lower()) if t not in _STOP]


def rrf(rank_lists: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal rank fusion over ranked id lists -> [(id, score)] desc."""
    scores: dict[str, float] = {}
    for ranked in rank_lists:
        for rank, cid in enumerate(ranked):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: -kv[1])


class HybridIndex:
    """BM25 (+ optional dense) index over a fixed chunk list."""

    def __init__(
        self,
        chunks: list[Chunk],
        persist_dir: Path | str | None = None,
        embed_model: str | None = None,
    ) -> None:
        self.chunks: list[Chunk] = list(chunks)
        self.by_id: dict[str, Chunk] = {c.chunk_id: c for c in self.chunks}
        self.persist_dir = Path(persist_dir) if persist_dir else get_chroma_dir()
        self.embed_model = embed_model or get_embed_model()
        self._bm25 = self._build_bm25()
        self._tf_fallback_used = self._bm25 is None
        self._dense_ok = False
        self._collection = None
        self._reranker = None

    # -- lexical (always available) -------------------------------------
    def _build_bm25(self):
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            return None
        corpus = [_tokens(c.text) for c in self.chunks]
        if not any(corpus):
            return None
        return BM25Okapi(corpus)

    def _bm25_rank(
        self, query: str, pool_idx: list[int], min_overlap: int = 2,
        min_coverage: float | None = None,
    ) -> list[str]:
        """Lexical leg: rank by BM25, keep docs clearing the overlap gate.

        Gate is proportional: required = min(min_overlap, #distinct query
        tokens), so a genuine single-term query must match fully while
        multi-token noise sharing one term still refuses. min_coverage
        (None -> MIN_COVERAGE env) additionally requires that fraction of
        distinct query tokens in the chunk — the trap lever for queries
        sharing 3-4 content words. Section-label bypass mirrors
        retrieval/store.py. The dense leg is NOT gated here: embeddings
        match paraphrases that share no tokens by design (gated instead by
        RERANK_MIN_SCORE in _rerank).
        """
        if min_coverage is None:
            from generation.config import get_min_coverage

            min_coverage = get_min_coverage()
        if not pool_idx:
            return []
        qtok = _tokens(query)
        if not qtok:
            return []
        required = min(min_overlap, len(set(qtok)))
        qdistinct = set(qtok)
        qlower = query.lower()
        if self._bm25 is None:  # pure-python TF fallback
            from collections import Counter

            qcount = Counter(qtok)
            scored = []
            for i in pool_idx:
                cc = Counter(_tokens(self.chunks[i].text))
                overlap = {t for t in qcount if t in cc}
                label = self.chunks[i].section_label
                if label and label.lower() in qlower:
                    pass  # explicit section ask: skip both gates
                elif len(overlap) < required:
                    continue
                elif len(overlap) / len(qdistinct) < min_coverage:
                    continue
                s = sum(min(qcount[t], cc[t]) for t in overlap)
                if label and label.lower() in qlower:
                    s += 3  # mirrors retrieval/store.py section bonus
                if s > 0:
                    scored.append((s, self.chunks[i].chunk_id))
            scored.sort(key=lambda x: (-x[0], x[1]))
            return [cid for _, cid in scored]
        import numpy as np  # noqa: F401  (rank_bm25 dependency)

        scores = self._bm25.get_scores(qtok)
        # NOTE: BM25 scores can be negative on tiny corpora (IDF with N=1),
        # so rank by score but keep docs clearing the overlap gate instead
        # of filtering on score > 0.
        qset = set(qtok)
        ranked = sorted(pool_idx, key=lambda i: (-scores[i], self.chunks[i].chunk_id))
        out = []
        for i in ranked:
            label = self.chunks[i].section_label
            if label and label.lower() in qlower:
                out.append(self.chunks[i].chunk_id)  # explicit section ask
                continue
            overlap = qset & set(_tokens(self.chunks[i].text))
            if len(overlap) < required:
                continue
            if len(overlap) / len(qset) < min_coverage:
                continue
            out.append(self.chunks[i].chunk_id)
        return out

    # -- dense (optional, cached on disk) --------------------------------
    def _dense_enabled(self) -> bool:
        return self.embed_model not in ("", "tfidf-local", "none")

    def _ensure_dense(self) -> bool:
        if self._dense_ok or not self._dense_enabled() or not self.chunks:
            return self._dense_ok
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return False
        try:
            model = SentenceTransformer(self.embed_model)
            client = chromadb.PersistentClient(path=str(self.persist_dir))
            col = client.get_or_create_collection("chunks")
            have = set(col.get(ids=[c.chunk_id])["ids"])
            missing = [c for c in self.chunks if c.chunk_id not in have]
            if missing:
                embs = model.encode(
                    [c.text for c in missing], show_progress_bar=False
                ).tolist()
                col.add(
                    ids=[c.chunk_id for c in missing],
                    documents=[c.text for c in missing],
                    embeddings=embs,
                    metadatas=[
                        {"doc_id": c.doc_id, "page": c.page or 0} for c in missing
                    ],
                )
            self._embed = model.encode  # type: ignore[attr-defined]
            self._collection = col
            self._dense_ok = True
        except Exception:
            self._dense_ok = False
        return self._dense_ok

    def _dense_rank(self, query: str, pool_doc_ids: set[str], n: int) -> list[str]:
        """Rank via Chroma, filtered to pool docs; returns chunk_ids in pool."""
        if not self._ensure_dense() or not pool_doc_ids:
            return []
        try:
            where = {"doc_id": {"$in": sorted(pool_doc_ids)}}
            qemb = self._embed([query], show_progress_bar=False).tolist()  # type: ignore[attr-defined]
            res = self._collection.query(  # type: ignore[union-attr]
                query_embeddings=qemb, n_results=n, where=where
            )
            pool_ids = {c.chunk_id for c in self.chunks if c.doc_id in pool_doc_ids}
            return [cid for cid in res["ids"][0] if cid in pool_ids]
        except Exception:
            return []

    # -- rerank (optional) ------------------------------------------------
    def _rerank(
        self,
        query: str,
        ranked: list[tuple[str, float]],
        min_score: float | None = None,
    ) -> list[tuple[str, float]]:
        """Cross-encoder rerank; drop chunks below RERANK_MIN_SCORE.

        The dense leg is ungated by token overlap by design, so this cutoff
        is its gate: paraphrases the model scores below cutoff are dropped,
        and an emptied list refuses downstream. Without the reranker lib
        there is no gate (returned unchanged).
        """
        if len(ranked) < 2:
            return ranked
        if min_score is None:
            from generation.config import get_rerank_min_score

            min_score = get_rerank_min_score()
        try:
            from sentence_transformers import CrossEncoder

            if self._reranker is None:
                self._reranker = CrossEncoder(get_reranker_model())
            pairs = [(query, self.by_id[cid].text) for cid, _ in ranked]
            scores = self._reranker.predict(pairs)
            out = sorted(zip([c for c, _ in ranked], scores), key=lambda x: -x[1])
            return [(cid, float(s)) for cid, s in out if float(s) >= min_score]
        except Exception:
            return ranked

    # -- public API --------------------------------------------------------
    def retrieve(
        self,
        query: str,
        top_k: int = 8,
        doc_ids: list[str] | None = None,
        min_overlap: int = 2,
        min_coverage: float | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Fuse BM25 + dense via RRF, rerank, return [(Chunk, score)]."""
        allowed = set(doc_ids) if doc_ids else None
        pool_idx = [
            i for i, c in enumerate(self.chunks)
            if allowed is None or c.doc_id in allowed
        ]
        if not pool_idx or not _tokens(query):
            return []
        self._tf_fallback_used = self._bm25 is None
        pool_ids = {self.chunks[i].chunk_id for i in pool_idx}
        pool_docs = {self.chunks[i].doc_id for i in pool_idx}
        bm25_rank = self._bm25_rank(
            query, pool_idx, min_overlap=min_overlap, min_coverage=min_coverage
        )
        dense_rank = [
            cid for cid in self._dense_rank(query, pool_docs, n=max(top_k * 3, 20))
            if cid in pool_ids
        ]
        fused = rrf([r for r in (bm25_rank, dense_rank) if r])
        # Section-label bonus, counted ONCE: the TF fallback leg already
        # adds +3 (mirroring store.py), so skip the fused +0.05 there.
        if not self._tf_fallback_used:
            fused = self._label_bonus(query, fused)
        final = self._rerank(query, fused[: max(top_k * 3, top_k)])
        return [(self.by_id[cid], score) for cid, score in final[:top_k]]

    def _label_bonus(
        self, query: str, fused: list[tuple[str, float]]
    ) -> list[tuple[str, float]]:
        q = query.lower()
        boosted = []
        for cid, s in fused:
            c = self.by_id[cid]
            if c.section_label and c.section_label.lower() in q:
                s += 0.05
            boosted.append((cid, s))
        boosted.sort(key=lambda x: -x[1])
        return boosted


_INDEX: HybridIndex | None = None


def _registry_chunks(base: Path | str | None = None) -> list[Chunk]:
    """Seed + processed chunks, mirroring api/main.py:_registry (same upsert order).

    _default_chunks used to return *only* processed JSONL when present, so the
    hybrid index silently lacked seed docs (bnss_2023, sc_bail_2022,
    case_file_demo) and any doc_ids-filtered query on them refused.
    """
    from ingest.pipeline import load_chunks, load_docs
    from ingest.seed import load_seeds

    root = Path(base) if base is not None else Path(__file__).resolve().parent.parent
    reg = load_seeds(root / "data")
    for doc in load_docs(root):  # ingested files upsert over seeds on collision
        reg.chunks = {cid: c for cid, c in reg.chunks.items() if c.doc_id != doc.doc_id}
        reg.register_doc(doc)
    for chunk in load_chunks(root):
        if chunk.doc_id in reg.docs:
            reg.chunks[chunk.chunk_id] = chunk
    return list(reg.chunks.values())


def _default_chunks() -> list[Chunk]:
    """Seed + processed union (works offline: seeds alone when no JSONL)."""
    return _registry_chunks()


def get_index() -> HybridIndex:
    """Process-wide singleton (rebuilt after ingest via rebuild_index)."""
    global _INDEX
    if _INDEX is None:
        _INDEX = HybridIndex(_default_chunks())
    return _INDEX


def rebuild_index() -> HybridIndex:
    """Drop the cached index so new ingests are picked up."""
    global _INDEX
    _INDEX = HybridIndex(_default_chunks())
    return _INDEX


def retrieve(
    query: str,
    top_k: int = 8,
    doc_ids: list[str] | None = None,
    min_overlap: int = 2,
    min_coverage: float | None = None,
) -> list[tuple[Chunk, float]]:
    """retrieve(query, top_k=8, doc_ids=None, min_overlap=2, min_coverage=None)."""
    return get_index().retrieve(
        query, top_k=top_k, doc_ids=doc_ids,
        min_overlap=min_overlap, min_coverage=min_coverage,
    )
