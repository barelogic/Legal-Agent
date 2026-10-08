"""Pure render helpers: verifiability rules enforced BEFORE Streamlit.

Grounding rule: a claim is renderable as a fact ONLY if it carries at
least one ``chunk_id`` AND a non-empty verbatim ``quote``. Anything else
raises and must be shown as dropped/refused, never as a fact.
"""

from __future__ import annotations

import html
import re

from contracts.schemas import Answer, Citation, Claim, Doc

MARKER_RE = re.compile(r"\[(c\d+)\]")

STATUS_BADGE: dict[str, str] = {
    "verified": "✅ verified",
    "unsupported": "⚠️ unsupported",
    "removed": "⛔ removed",
    "unverified": "❔ unverified",
}


def docs_by_id(docs: list[Doc]) -> dict[str, Doc]:
    """Index Docs by doc_id for source resolution."""
    return {d.doc_id: d for d in docs}


def doc_id_of_chunk(chunk_id: str) -> str:
    """Extract doc_id from a ``{doc_id}::...`` chunk id (fallback '')."""
    return chunk_id.split("::")[0] if "::" in chunk_id else ""


def validate_claim_renderable(claim: Claim) -> None:
    """Raise ValueError if the claim must not be shown as a verified fact."""
    if not claim.chunk_ids:
        raise ValueError(f"claim {claim.claim_id} has no chunk_ids: refusing to render")
    if not claim.quote.strip():
        raise ValueError(f"claim {claim.claim_id} has no quote: refusing to render")


def source_label(chunk_id: str, docs: dict[str, Doc]) -> str:
    """Human-readable source label, honest when Doc metadata is missing."""
    doc = docs.get(doc_id_of_chunk(chunk_id))
    if doc is None:
        return f"{chunk_id} (unregistered doc)"
    bits = [doc.title]
    if doc.citation:
        bits.append(doc.citation)
    return f"{' — '.join(bits)} · `{chunk_id}`"


def claim_to_markdown(claim: Claim, docs: dict[str, Doc]) -> str:
    """Render ONE verified claim with its quote + source links. No source → raise."""
    validate_claim_renderable(claim)
    lines = [claim.text, ""]
    lines.append(f"> {claim.quote}")
    lines.append("")
    for cid in claim.chunk_ids:
        lines.append(f"- Source: {source_label(cid, docs)}")
        doc = docs.get(doc_id_of_chunk(cid))
        if doc is not None and doc.source_url:
            lines.append(f"  <{doc.source_url}|open source>")
        else:
            lines.append("  _local doc — no external link_")
    if claim.verifier_note:
        lines.append(f"\n_Verifier: {claim.verifier_note}_")
    return "\n".join(lines)


def citation_to_markdown(cite: Citation, docs: dict[str, Doc]) -> str:
    """Render one citation; unresolved citations are flagged, never linked."""
    if not cite.resolved or not cite.doc_id or cite.doc_id not in docs:
        return f"`{cite.raw}` → ⚠️ unresolved (not in registry)"
    doc = docs[cite.doc_id]
    if doc.source_url:
        return f"`{cite.raw}` → [{doc.title}]({doc.source_url})"
    cited = f" ({doc.citation})" if doc.citation else ""
    return f"`{cite.raw}` → {doc.title}{cited} · `{doc.doc_id}` (local doc)"


def verified_claims(answer: Answer) -> list[Claim]:
    """Claims safe to show as facts (verified + renderable)."""
    out = []
    for c in answer.claims:
        if c.status != "verified":
            continue
        try:
            validate_claim_renderable(c)
        except ValueError:
            continue
        out.append(c)
    return out


def dropped_claims(answer: Answer) -> list[Claim]:
    """Everything else: audit trail, shown collapsed — never as facts."""
    v_ids = {c.claim_id for c in verified_claims(answer)}
    return [c for c in answer.claims if c.claim_id not in v_ids]


def split_text_markers(text: str) -> list[tuple[str, str | None]]:
    """Split ``Answer.text`` into (segment, claim_id|None) parts on [cN]."""
    parts: list[tuple[str, str | None]] = []
    last = 0
    for m in MARKER_RE.finditer(text):
        if m.start() > last:
            parts.append((text[last:m.start()], None))
        parts.append((m.group(0), m.group(1)))
        last = m.end()
    if last < len(text):
        parts.append((text[last:], None))
    if not parts:
        parts.append((text, None))
    return parts


def claim_markers(text: str) -> list[str]:
    """Ordered unique claim ids referenced as [cN] in text."""
    seen: list[str] = []
    for m in MARKER_RE.finditer(text):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def highlight_quote(chunk_text: str, quote: str) -> str:
    """Escape HTML and wrap the first verbatim quote occurrence in <mark>."""
    safe = html.escape(chunk_text)
    q = html.escape(quote)
    if quote and quote in chunk_text and q in safe:
        return safe.replace(q, f"<mark>{q}</mark>", 1)
    return safe


def status_badge(status: str) -> str:
    """Badge label for a claim status; unknown statuses pass through."""
    return STATUS_BADGE.get(status, status)
