"""Citation gate: a citation is allowed ONLY if it resolves to a Doc in the registry.

Anything the model emits that does not match a registered Doc (by doc_id,
canonical citation string, or title) stays unresolved and must be excluded
from the final Answer.
"""

from contracts.schemas import Chunk, Citation, Claim, Doc


def resolve_raw(raw: str, docs: dict[str, Doc]) -> Doc | None:
    """Match a raw citation string to a registered Doc, else None."""
    key = " ".join(raw.split()).casefold()
    if not key:
        return None
    for d in docs.values():
        if key == d.doc_id.casefold():
            return d
        if d.citation and key == " ".join(d.citation.split()).casefold():
            return d
        if key == " ".join(d.title.split()).casefold():
            return d
    # allow "see <doc_id>" style mentions: substring match on doc_id
    for d in docs.values():
        if d.doc_id.casefold() in key:
            return d
    return None


def build_citations(
    claims: list[Claim],
    chunk_map: dict[str, Chunk],
    docs: dict[str, Doc],
) -> list[Citation]:
    """Derive one Citation per distinct doc backing the verified claims.

    Only resolved citations are returned; unresolved ones are dropped.
    """
    seen: dict[str, Citation] = {}
    for cl in claims:
        for cid in cl.chunk_ids:
            ch = chunk_map.get(cid)
            if ch is None or ch.doc_id not in docs:
                continue
            if ch.doc_id in seen:
                continue
            doc = docs[ch.doc_id]
            raw = doc.citation or doc.doc_id
            seen[ch.doc_id] = Citation(
                cite_id=ch.doc_id,
                raw=raw,
                doc_id=doc.doc_id,
                resolved=True,
            )
    return list(seen.values())


def gate_citations(
    citations: list[Citation], docs: dict[str, Doc]
) -> list[Citation]:
    """Re-resolve model-supplied citations; keep only resolved ones."""
    kept: list[Citation] = []
    for c in citations:
        doc = None
        if c.doc_id and c.doc_id in docs:
            doc = docs[c.doc_id]
        else:
            doc = resolve_raw(c.raw, docs)
        if doc is None:
            continue
        kept.append(c.model_copy(update={"doc_id": doc.doc_id, "resolved": True}))
    return kept
