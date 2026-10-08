"""Review workflow: verified key facts per doc + deterministic contradictions.

For each doc in doc_ids the normal claims -> verify pipeline extracts key
facts (parties, dates, sections, amounts, custody status); only verified
claims are returned. Expected case-file elements (FIR, charge sheet,
remand order, medical report) absent from a doc's text yield MissingInfo.

Contradictions come from deterministic regexes over verified claims only:
dates, amounts, FIR numbers, ages, section numbers, grouped by the nearby
attribute phrase. Two docs giving different values for the same attribute
emit Contradiction(description, claim_a, claim_b) with real chunk_ids.
Conservative by design: prefer a missed contradiction over a false one
(values must carry digits/markers; cross-doc pairs only).
"""

import re
import time

from contracts.schemas import Answer, Claim, Contradiction, MissingInfo
from verify import flags as vflags
from verify.citations import build_citations
from workflows._ground import renumber_claims, verified_only
from workflows.answer import REFUSAL, answer_from_chunks

KEYFACT_QUESTION = (
    "List the key facts of this case file: parties, dates, sections, amounts, custody status."
)

# Expected elements: (field label, keyword variants searched in doc text).
EXPECTED_ELEMENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("FIR", ("fir",)),
    ("charge sheet", ("charge sheet", "chargesheet", "charge-sheet")),
    ("remand order", ("remand",)),
    ("medical report", ("medical",)),
)

_DATE_RE = r"(?:\d{1,2}[-/.\s]\d{1,2}[-/.\s]\d{2,4}|\d{4}-\d{2}-\d{2})"
_FIR_RE = re.compile(r"FIR\s*(?:No\.?|number)?\s*[:\-]?\s*([A-Za-z0-9][\w\/\-\.]*)", re.I)
_DATE_ATTRS = (
    (re.compile(r"(date of arrest|arrest date)[^\n.]{0,40}?(" + _DATE_RE + r")", re.I), "date of arrest"),
    (re.compile(r"(date of FIR|FIR date|date of registration|FIR registered on)[^\n.]{0,40}?(" + _DATE_RE + r")", re.I), "date of FIR"),
    (re.compile(r"(date of remand|remand date)[^\n.]{0,40}?(" + _DATE_RE + r")", re.I), "date of remand"),
    (re.compile(r"(date of custody|custody date)[^\n.]{0,40}?(" + _DATE_RE + r")", re.I), "date of custody"),
)
_AMOUNT_RE = re.compile(
    r"\b(bond|surety|fine|compensation|personal bond|bail bond)\b[^\n.]{0,40}?\bRs\.?\s*([\d,]+)",
    re.I,
)
_AGE_RES = (
    re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}),?\s+aged?\s*(\d{1,3})\b"),
    re.compile(r"\bage\s+of\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+(?:is|:)?\s*(\d{1,3})\b", re.I),
)
_SECTION_RE = re.compile(
    r"\bSection\s*(\d+[A-Za-z]?(?:\(\d+\))?)\s*(?:of\s+(?:the\s+)?([A-Za-z][\w&.\-]*(?:\s+[A-Za-z][\w&.\-]*){0,3}))?",
    re.I,
)


def _norm_digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def extract_attribute_values(text: str) -> list[tuple[str, str, str]]:
    """Deterministic (attribute, norm_value, raw_value) pairs from claim text."""
    out: list[tuple[str, str, str]] = []
    for m in _FIR_RE.finditer(text or ""):
        raw = m.group(1).strip(" ,;.\"'()")
        if re.search(r"\d", raw):  # FIR numbers carry digits; "FIR registered" is not one
            out.append(("FIR number", raw.casefold(), raw))
    for rx, attr in _DATE_ATTRS:
        for m in rx.finditer(text or ""):
            raw = m.group(2)
            out.append((attr, _norm_digits(raw), raw))
    for m in _AMOUNT_RE.finditer(text or ""):
        raw = m.group(2)
        out.append((f"{m.group(1).casefold()} amount", _norm_digits(raw), f"Rs. {raw}"))
    for rx in _AGE_RES:
        for m in rx.finditer(text or ""):
            out.append((f"age of {m.group(1)}", m.group(2), f"{m.group(1)}, {m.group(2)}"))
    for m in _SECTION_RE.finditer(text or ""):
        num = m.group(1).casefold()
        act = (m.group(2) or "").strip()
        attr = f"section of {act.casefold()}" if act else "section (act unspecified)"
        out.append((attr, num, m.group(0).strip()))
    return out


def find_contradictions(claims: list[Claim]) -> list[Contradiction]:
    """Group (attribute, value) pairs; cross-doc disagreements contradict.

    Only verified claims are passed in by run_review; chunk_ids are real by
    construction (the verifier rejects unknown chunk_ids).
    """
    by_attr: dict[str, list[tuple[str, str, str, str]]] = {}
    for c in claims:
        doc = c.chunk_ids[0].split("::")[0] if c.chunk_ids else ""
        for attr, norm, raw in extract_attribute_values(c.text):
            by_attr.setdefault(attr, []).append((norm, raw, c.chunk_ids[0], doc))
    out: list[Contradiction] = []
    seen: set[tuple[str, str, str]] = set()
    for attr, rows in by_attr.items():
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                ni, rawi, cidi, doci = rows[i]
                nj, rawj, cidj, docj = rows[j]
                if doci == docj or ni == nj:
                    continue
                key = (attr, doci, docj)
                if key in seen:
                    continue
                seen.add(key)
                out.append(Contradiction(
                    description=f"{attr}: {rawi!r} in {doci} vs {rawj!r} in {docj}",
                    claim_a=cidi,
                    claim_b=cidj,
                ))
    return out


def run_review(
    *,
    doc_ids: list[str] | None,
    registry,
    llm,
    flagset: dict[str, bool] | None = None,
    top_k: int = 8,
) -> Answer:
    """Verified key facts per doc, missing elements, cross-doc contradictions."""
    t0 = time.perf_counter()
    flagset = flagset if flagset is not None else vflags.all_flags()
    doc_ids = list(doc_ids or [])

    per_doc_verified: dict[str, list[Claim]] = {}
    failed: list[Claim] = []
    missing: list[MissingInfo] = []

    for doc_id in doc_ids:
        if doc_id not in registry.docs:
            missing.append(MissingInfo(
                field=doc_id, why_needed="unknown doc_id; not in registry", searched_in=[]))
            continue
        chunks = [c for c in registry.chunks.values() if c.doc_id == doc_id]
        if not chunks:
            missing.append(MissingInfo(
                field=f"{doc_id}: case file", why_needed="no chunks registered",
                searched_in=[doc_id]))
            continue
        ans = answer_from_chunks(
            f"{KEYFACT_QUESTION} ({doc_id})", "review", registry, llm,
            chunks[: max(top_k * 3, top_k)], flagset=flagset,
        )
        good = verified_only(ans.claims)
        per_doc_verified[doc_id] = good
        failed.extend(c for c in ans.claims if c.status != "verified")
        if not good:
            missing.append(MissingInfo(
                field=f"{doc_id}: key facts",
                why_needed="no verifiable key-fact claim in this document",
                searched_in=[doc_id]))
        blob = "\n".join(c.text for c in chunks).casefold()
        for label, variants in EXPECTED_ELEMENTS:
            if not any(v in blob for v in variants):
                missing.append(MissingInfo(
                    field=label,
                    why_needed=f"expected case-file element not found in {doc_id}",
                    searched_in=[doc_id]))

    ordered = [c for d in doc_ids for c in per_doc_verified.get(d, [])]
    claims = renumber_claims(ordered)
    contradictions = find_contradictions(claims)
    chunk_map = {cid: registry.chunks[cid] for c in claims for cid in c.chunk_ids if cid in registry.chunks}
    citations = build_citations(claims, chunk_map, registry.docs)
    total = len(claims) + len(failed)
    ms = int((time.perf_counter() - t0) * 1000)
    trace = {
        "doc_ids": doc_ids,
        "per_doc_counts": {d: len(per_doc_verified.get(d, [])) for d in doc_ids},
        "flags": dict(flagset),
        "latency_ms": ms,
    }
    if not claims:
        return Answer(
            workflow="review",
            text=REFUSAL,
            claims=failed,
            citations=[],
            missing_info=missing,
            contradictions=[],
            confidence=(0.0 if total else None),
            refused=True,
            refusal_reason="no verifiable key-fact claim in the given documents",
            trace=trace,
        )
    parts: list[str] = []
    it = iter(claims)
    renumbered = {d: [next(it) for _ in per_doc_verified.get(d, [])] for d in doc_ids}
    for d in doc_ids:
        parts.append(f"## {d}")
        if renumbered.get(d):
            for c in renumbered[d]:
                parts.append(f"- {c.text} [{c.claim_id}]")
        else:
            parts.append("- no verified facts")
        parts.append("")
    parts.append("Sources:")
    for c in claims:
        parts.append(f"[{c.claim_id}] {', '.join(c.chunk_ids)}: \"{c.quote}\"")
    return Answer(
        workflow="review",
        text="\n".join(parts),
        claims=claims,
        citations=citations,
        missing_info=missing,
        contradictions=contradictions,
        confidence=(len(claims) / total if total else None),
        refused=False,
        trace=trace,
    )
