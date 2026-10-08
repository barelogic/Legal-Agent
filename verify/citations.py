"""Citation gate: a citation is allowed ONLY if it resolves to a Doc in the registry.

Anything the model emits that does not match a registered Doc (by doc_id,
canonical citation string, or title) stays unresolved and must be excluded
from the final Answer.
"""

import re

from contracts.schemas import Chunk, Citation, Claim, Doc
from ingest.normalize import canonicalize
from verify.textcheck import strip_leading_dust

# Citation-like strings inside claim.text that must each resolve to a Doc
# AND appear in the quote or a cited chunk. Bare "Section N" (no Act) is
# NOT a citation mention — verify/textcheck.py already requires the number
# to appear in the quote.
_SECTION_OF_ACT_RE = re.compile(
    r"\bSection\s+\d+[A-Za-z]?(?:\(\d+\))?\s+of\s+(?:the\s+)?"
    r"[A-Z][\w&.-]*(?:\s+(?:of\s+|the\s+)?[A-Z0-9][\w&.-]*){0,6}"
)
_CASE_CITE_RE = re.compile(
    r"\b[A-Z][\w&'.-]*(?:\s+[A-Z][\w&'.-]*)*\s+v\.?\s+[A-Z][\w&'.-]*"
    r"(?:\s+(?:of\s+)?[A-Z][\w&'.-]*)*"
)
_REPORTER_RES = (
    re.compile(r"\(\d{4}\)\s*\d+\s*SCC\s*\d+"),
    re.compile(r"\bAIR\s+\d{4}\s+[A-Z&]+\s+\d+"),
)


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
    # allow "see <doc_id>" style mentions: doc_id as a whole word only.
    # The old substring fallback matched "bnss_2023" inside "xbnss_2023y",
    # letting fabricated cites ride on real doc_id fragments.
    for d in docs.values():
        if re.search(r"\b" + re.escape(d.doc_id.casefold()) + r"\b", key):
            return d
    return None


def resolve_mention(mention: str, docs: dict[str, Doc]) -> Doc | None:
    """Resolve a citation-like mention (case name, Act ref, reporter cite).

    resolve_raw first (exact doc_id / citation / title); then normalised
    containment either direction (case names gain "(year)" suffixes in the
    registry; Act mentions are prefixes of titles). Short mentions (<8
    chars) never containment-match — "Court" must not match everything.
    """
    direct = resolve_raw(mention, docs)
    if direct is not None:
        return direct
    key = " ".join(mention.split()).casefold()
    core = re.sub(r"\s*\(\d{4}\)\s*", " ", key).strip()
    if len(core) < 8:
        return None
    for d in docs.values():
        cands = (
            d.citation or "",
            d.title or "",
            d.doc_id.replace("_", " "),
        )
        for cand in cands:
            c = " ".join(cand.split()).casefold()
            if c and (core in c or c in core):
                return d
    # "Section N of <Act>": the whole string never equals a title, so also
    # try resolving the Act part alone ("... of the Bharatiya Nagarik ...").
    m = _SECTION_OF_ACT_RE.search(mention)
    if m:
        act = re.split(r"\bof\b", m.group(0), maxsplit=1)[-1]
        act = re.sub(r"^\s*the\s+", "", act.strip(" ,;.\"'()"))
        if act and act.casefold() != key:
            return resolve_mention(act, docs)
    return None


def extract_citation_mentions(text: str) -> list[str]:
    """Citation-like strings in claim.text ("Section N of <Act>", "X v. Y",
    "(YYYY) N SCC N", "AIR ..."). De-duplicated, in order."""
    out: list[str] = []
    seen: set[str] = set()
    patterns: tuple = (_SECTION_OF_ACT_RE, _CASE_CITE_RE, *_REPORTER_RES)
    for rx in patterns:
        for m in rx.finditer(text or ""):
            item = strip_leading_dust(m.group(0).strip(" ,;.\"'()"))
            if item and item.casefold() not in seen:
                seen.add(item.casefold())
                out.append(item)
    return out


def gate_claim_citations(
    text: str,
    quote: str,
    cited_chunks: list[Chunk],
    docs: dict[str, Doc],
) -> str | None:
    """Citation gate for one claim. Returns a failure reason, or None if clean.

    Every citation-like string in claim.text must resolve to a registry Doc
    AND appear (normalised) in the quote or one of the cited chunks.
    """
    mentions = extract_citation_mentions(text)
    if not mentions:
        return None
    nq = canonicalize(quote, fold_case=True)
    chunk_texts = [canonicalize(c.text, fold_case=True) for c in cited_chunks]
    for m in mentions:
        if resolve_mention(m, docs) is None:
            return f"unresolved citation: {m!r} (no registry Doc)"
        nm = canonicalize(m, fold_case=True)
        if nm not in nq and not any(nm in ct for ct in chunk_texts):
            return f"citation {m!r} not found in cited sources"
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
