"""Pure render helpers: verifiability rules enforced BEFORE Streamlit.

Grounding rule: a claim is renderable as a fact ONLY if it carries at
least one ``chunk_id`` AND a non-empty verbatim ``quote``. Anything else
raises and must be shown as dropped/refused, never as a fact.
"""

from __future__ import annotations

import difflib
import html
import json
import re
from pathlib import Path

from contracts.schemas import Answer, Citation, Claim, Contradiction, Doc

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


# Distinct visual lane for user-supplied values (question text, draft field
# inputs, case-set choices). Amber/brown — never the green/blue used for
# sourced facts — plus an explicit "user-provided" label so a judge can
# never mistake typed input for a retrieved fact.
USER_VALUE_CSS = (
    "<style>"
    ".user-provided { background: #fef3c7; color: #92400e;"
    " border: 1px solid #f59e0b; border-radius: 6px;"
    " padding: 2px 8px; font-size: 0.85em; }"
    ".user-provided-tag { background: #92400e; color: #fff8e6;"
    " border-radius: 4px; padding: 0 6px; margin-right: 6px;"
    " font-size: 0.75em; font-weight: 600; }"
    ".sourced { text-decoration: underline dotted #16a34a 2px;"
    " text-underline-offset: 3px; cursor: help; }"
    ".missing-chip { background: #fee2e2; color: #991b1b;"
    " border: 1px solid #ef4444; border-radius: 6px;"
    " padding: 2px 8px; font-size: 0.85em; font-weight: 600; }"
    "</style>"
)


def user_value_html(value: str) -> str:
    """Wrap a user-supplied value in a visually distinct badge.

    HTML-escaped; always carries the ``user-provided`` label. Pure function
    so tests pin the distinction without Streamlit.
    """
    return (
        '<span class="user-provided"><span class="user-provided-tag">'
        "user-provided</span>"
        f"{html.escape(value)}</span>"
    )


def user_provided_chip(value: str) -> str:
    """Inline ``[USER-PROVIDED: value]`` marker in the user-value style.

    Used in draft views for values the user typed into the missing-info
    panel. Never a sourced fact: the label says who provided it.
    """
    return (
        '<span class="user-provided"><span class="user-provided-tag">'
        "user-provided</span>"
        f"[USER-PROVIDED: {html.escape(value)}]</span>"
    )


def missing_chip(field: str) -> str:
    """Inline red ``[MISSING: field]`` placeholder for unsourced items."""
    return f'<span class="missing-chip">[MISSING: {html.escape(field)}]</span>'


# ---------------------------------------------------------------------------
# Templates + precheck (pure; templates/*.json are UI-owned content)
# ---------------------------------------------------------------------------

TEMPLATE_IDS = ("bail_application", "legal_notice", "affidavit")


def _templates_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"


def load_template(template_id: str) -> dict:
    """Load one UI-owned template JSON; raises ValueError if unknown."""
    if template_id not in TEMPLATE_IDS:
        raise ValueError(f"unknown template {template_id!r}")
    return json.loads((_templates_dir() / f"{template_id}.json").read_text(encoding="utf-8"))


def required_fields(template: dict) -> list[dict]:
    """Required field dicts of a template JSON (in file order)."""
    return [f for f in template.get("required_fields", []) if f.get("required")]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _field_flagged(norm_name: str, missing: list) -> object | None:
    """Return the MissingInfo entry flagging this template field, if any."""
    for m in missing:
        nm = _norm(m.field)
        if not nm or not norm_name:
            continue
        if nm == norm_name or nm in norm_name or norm_name in nm:
            return m
    return None


def precheck_summary(answer: Answer, template: dict) -> dict:
    """Draft readiness derived client-side from an Answer + template.

    ``sourced`` = required field the backend did NOT flag in
    ``missing_info``. ``unconfirmed`` is True when the backend returned no
    missing-info list at all — then nothing was flagged, so callers must
    label the count as unconfirmed, never as proven.
    """
    fields = required_fields(template)
    rows: list[dict] = []
    for f in fields:
        m = _field_flagged(_norm(f["name"]), answer.missing_info)
        rows.append(
            {
                "name": f["name"],
                "description": f.get("description", ""),
                "status": "missing" if m is not None else "sourced",
                "why_needed": m.why_needed if m is not None else "",
                "searched_in": list(m.searched_in) if m is not None else [],
            }
        )
    sourced_n = sum(1 for r in rows if r["status"] == "sourced")
    return {
        "template_id": template.get("template_id", ""),
        "total": len(rows),
        "sourced_n": sourced_n,
        "missing_n": len(rows) - sourced_n,
        "unconfirmed": not answer.missing_info,
        "rows": rows,
    }


def confidence_text(answer: Answer) -> str:
    """Honest one-line confidence readout (backend often sends None)."""
    if answer.confidence is None:
        return "confidence: not provided by backend"
    return f"confidence: {answer.confidence:.2f}"


# ---------------------------------------------------------------------------
# Draft view (pure HTML; Streamlit chips stay as buttons in app.py)
# ---------------------------------------------------------------------------

def _claims_by_id(answer: Answer) -> dict[str, Claim]:
    return {c.claim_id: c for c in answer.claims}


def draft_html(answer: Answer) -> str:
    """Render Answer.text as HTML: sourced runs underlined w/ quote tooltip.

    Text preceding each ``[cN]`` marker is wrapped in
    ``<span class="sourced" title="verbatim quote">`` — hover previews the
    quote, and app.py adds a clickable chip button per marker. Runs with no
    following marker, or markers with no renderable claim, stay plain:
    never underlined without a quote to show.
    """
    by_id = _claims_by_id(answer)
    out: list[str] = []
    buf = ""

    def flush(marker_cid: str | None) -> None:
        nonlocal buf
        if not buf:
            return
        claim = by_id.get(marker_cid) if marker_cid else None
        quote = claim.quote if claim is not None else ""
        try:
            if claim is not None:
                validate_claim_renderable(claim)
            else:
                raise ValueError("no claim")
            out.append(
                f'<span class="sourced" title="{html.escape(quote)}">'
                f"{html.escape(buf)}</span>"
            )
        except ValueError:
            out.append(html.escape(buf))
        buf = ""

    for seg, cid in split_text_markers(answer.text):
        if cid is None:
            buf += seg
        else:
            flush(cid)
            out.append(f" <strong>[{cid}]</strong>")
    flush(None)
    return "".join(out)


def still_needed_html(answer: Answer, provided_values: dict[str, str]) -> str:
    """Red ``[MISSING: field]`` placeholders / amber user values, as HTML.

    One entry per ``missing_info`` item: a red placeholder when the user
    has not supplied the field, an amber ``[USER-PROVIDED: …]`` chip when
    they have. Empty string when the backend flagged nothing.
    """
    bits: list[str] = []
    for m in answer.missing_info:
        val = (provided_values or {}).get(m.field, "").strip()
        if val:
            bits.append(f"{missing_chip(m.field)} → {user_provided_chip(val)}")
        else:
            bits.append(missing_chip(m.field))
    return "<br>".join(bits)


# ---------------------------------------------------------------------------
# Verifier summary bar (trace-first, claims fallback — labelled either way)
# ---------------------------------------------------------------------------

def verifier_summary(answer: Answer) -> dict:
    """Verifier numbers for the summary bar, with provenance labels.

    ``dropped_n`` prefers ``trace["dropped"]`` (backend count) and falls
    back to the client-side dropped-claims count. ``dropped_reasons`` always
    come from claim ``status`` + ``verifier_note`` — the backend trace
    carries no per-claim reasons, and the label says so.
    """
    good = verified_claims(answer)
    bad = dropped_claims(answer)
    traced = answer.trace.get("dropped") if isinstance(answer.trace, dict) else None
    if isinstance(traced, int) and traced >= 0:
        dropped_n, source = traced, "trace"
    else:
        dropped_n, source = len(bad), "claims"
    reasons = [
        f"`{c.claim_id}` [{c.status}]"
        + (f" — {c.verifier_note}" if c.verifier_note else "")
        for c in bad
    ]
    return {
        "verified_n": len(good),
        "dropped_n": dropped_n,
        "dropped_source": source,
        "dropped_reasons": reasons,
        "reasons_source": "claim status/verifier notes (trace has no per-claim reasons)",
        "confidence": answer.confidence,
    }


def verifier_bar_html(summary: dict) -> str:
    """One-line HTML summary bar from :func:`verifier_summary`."""
    conf = (
        f"{summary['confidence']:.2f}"
        if summary["confidence"] is not None
        else "not provided"
    )
    return (
        f"✅ <strong>{summary['verified_n']}</strong> verified &nbsp;·&nbsp; "
        f"⛔ <strong>{summary['dropped_n']}</strong> dropped "
        f"(counted from {summary['dropped_source']}) &nbsp;·&nbsp; "
        f"confidence: <strong>{conf}</strong>"
    )


# ---------------------------------------------------------------------------
# Contradiction side-by-side (word diff; fetch stays in app.py for honesty)
# ---------------------------------------------------------------------------

def diff_sides(a: str, b: str) -> tuple[str, str]:
    """Word-level diff of two chunk texts; differing tokens get <mark>."""
    ta, tb = a.split(), b.split()
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    ha, hb = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            ha.extend(html.escape(t) for t in ta[i1:i2])
            hb.extend(html.escape(t) for t in tb[j1:j2])
        else:
            ha.extend(f"<mark>{html.escape(t)}</mark>" for t in ta[i1:i2])
            hb.extend(f"<mark>{html.escape(t)}</mark>" for t in tb[j1:j2])
    return " ".join(ha), " ".join(hb)


def contradiction_view_model(contra: Contradiction, fetched: dict[str, object | None]) -> dict:
    """View model for one contradiction: texts (or None when unfetched).

    ``fetched`` maps chunk_id → Chunk-like (``.text``) or None on failure.
    Pure: app.py does the ``/sources`` fetching, this decides what to show.
    """
    return {
        "description": contra.description,
        "chunk_a": contra.claim_a,
        "chunk_b": contra.claim_b,
        "text_a": getattr(fetched.get(contra.claim_a), "text", None),
        "text_b": getattr(fetched.get(contra.claim_b), "text", None),
    }
