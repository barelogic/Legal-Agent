"""Deterministic claim-text grounding (no LLM).

The old verifier only checked that claim.quote is a verbatim substring of a
cited chunk. claim.text is model-written, so a real quote could carry a
fabricated fact ("In Sharma v. Utopia (2024), bail is the rule" + a genuine
bail quote). This module closes that hole: every load-bearing item extracted
from claim.text — numbers, dates, section refs, money, case names, court
names, multi-word proper spans, acronyms — must appear in the normalised
quote. Anything missing marks the claim unsupported and names the item.

Deliberately conservative against over-refusal:
- single capitalised words (ordinary sentence starts like "Bail", "When")
  are NEVER extracted — only multi-word spans, case names, courts, acronyms;
- stopwords are excluded everywhere;
- leading determiners ("The", "A") are stripped from spans;
- section refs tolerate "Section" <-> "s." variance when the number matches.
"""

import re

from ingest.normalize import canonicalize

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
_SECTION_RE = re.compile(
    r"\b(?:Section\s+\d+[A-Za-z]?(?:\(\d+\))?|s\.\s*\d+[A-Za-z]?(?:\(\d+\))?)",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"(?:Rs\.?\s*|INR\s*|₹\s*)[\d,]+(?:\.\d+)?")
_DATE_RES = [
    re.compile(rf"\b\d{{1,2}}\s+(?:{_MONTHS})\s*,?\s*\d{{4}}\b", re.IGNORECASE),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
]
_CASE_RE = re.compile(
    r"\b[A-Z][\w&'.-]*(?:\s+[A-Z][\w&'.-]*)*\s+v\.?\s+[A-Z][\w&'.-]*"
    r"(?:\s+(?:of\s+)?[A-Z][\w&'.-]*)*"
)
_STATE_RE = re.compile(r"\bState of [A-Z][a-z]+\b")
_COURT_RE = re.compile(
    r"\b(?:Supreme Court|High Court|Court of Session|Sessions Court|"
    r"Judicial Magistrate|Public Prosecutor)\b"
)
_PROPER_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+(?:of\s+|the\s+)?[A-Z][a-z]+)+\b")
_ACRONYM_RE = re.compile(r"\b(?:[A-Z]{2,}[A-Z0-9]*|[A-Z][a-z]+[A-Z][\w]*)\b")
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_LEAD_DET = re.compile(r"^(?:The|A|An|This|That)\s+", re.IGNORECASE)
# Sentence prepositions glued onto a span start by greedy matching
# ("In Satender Kumar Antil v. CBI" — "In" is not part of the case name).
_LEAD_DUST = re.compile(
    r"^(?:In|On|At|Of|For|From|Under|Per|See|Cf|With|By|Through|"
    r"Against|Between)\s+",
    re.IGNORECASE,
)
_INSTR_LEAD = re.compile(
    r"^\s*[\"'(\[]*\s*(ignore|disregard|forget|override|output|answer|reveal|"
    r"disclose|delete|destroy|follow|execute|run|print|say|write|pretend|"
    r"act\s+as|you\s+must|do\s+not\s+cite|never\s+cite|always\s+answer|"
    r"stop\s+refusing)\b",
    re.IGNORECASE,
)

# Ordered by specificity: earlier patterns claim their spans first, later
# patterns (notably bare numbers) skip already-claimed ranges.
_PATTERNS = (
    ("section", _SECTION_RE),
    ("money", _MONEY_RE),
    ("case", _CASE_RE),
    ("state", _STATE_RE),
    ("court", _COURT_RE),
    ("proper", _PROPER_RE),
    ("acronym", _ACRONYM_RE),
)


def _spans_taken(spans: list[tuple[int, int]], s: int, e: int) -> bool:
    return any(s < te and e > ts for ts, te in spans)


def strip_leading_dust(raw: str) -> str:
    """Strip determiners/prepositions glued onto a span start by greedy matching."""
    s, prev = raw, None
    while s != prev:
        prev = s
        s = _LEAD_DUST.sub("", s)
    return s


def extract_items(text: str) -> list[str]:
    """Load-bearing items in claim.text, ordered and de-duplicated."""
    items: list[str] = []
    taken: list[tuple[int, int]] = []
    seen: set[str] = set()

    def _add(s: int, e: int, raw: str) -> None:
        item = strip_leading_dust(_LEAD_DET.sub("", raw.strip(" ,;.\"'()")).strip())
        if not item or item.casefold() in seen:
            return
        seen.add(item.casefold())
        taken.append((s, e))
        items.append(item)

    for _kind, rx in _PATTERNS:
        for m in rx.finditer(text):
            if _spans_taken(taken, m.start(), m.end()):
                continue
            _add(m.start(), m.end(), m.group(0))
    for rx in _DATE_RES:
        for m in rx.finditer(text):
            if _spans_taken(taken, m.start(), m.end()):
                continue
            _add(m.start(), m.end(), m.group(0))
    for m in _NUMBER_RE.finditer(text):
        if _spans_taken(taken, m.start(), m.end()):
            continue
        _add(m.start(), m.end(), m.group(0))
    return items


def _quote_numbers(norm_quote: str) -> set[str]:
    """Digit sequences in the quote, commas stripped ("2,50,000" -> "250000")."""
    return {m.group(0).replace(",", "") for m in _NUMBER_RE.finditer(norm_quote)}


def _section_present(item: str, norm_quote: str, qnums: set[str]) -> bool:
    num = re.search(r"(\d+[a-z]?(?:\(\d+\))?)\s*$", item.strip())
    if not num:
        return False
    core = num.group(1).replace(",", "")
    digits = re.sub(r"\D", "", core)
    if core in qnums or digits in qnums:
        # Number matches; tolerate "Section" <-> "s." variance.
        return "section" in norm_quote or re.search(r"\bs\.?\s*\d", norm_quote) is not None
    return False


def missing_from_quote(text: str, quote: str) -> list[str]:
    """Items in claim.text absent from the normalised quote (verbatim check).

    Substring after canonicalize+casefold — the same strictness as quote
    matching. No fuzzy matching by design.
    """
    nq = canonicalize(quote, fold_case=True)
    qnums = _quote_numbers(nq)
    missing: list[str] = []
    for item in extract_items(text or ""):
        ni = canonicalize(item, fold_case=True)
        if ni and ni in nq:
            continue
        if _SECTION_RE.fullmatch(item) and _section_present(item, nq, qnums):
            continue
        if re.fullmatch(r"[\d,.\s]+", item) and item.replace(",", "").strip() in qnums:
            continue
        missing.append(item)
    return missing


def looks_like_instruction(text: str) -> bool:
    """True if claim.text opens with an imperative (embedded-instruction smuggling).

    SOURCES are untrusted data; a "claim" that is really an instruction
    ("Ignore previous instructions and ...") must be dropped, never rendered.
    Declarative factual statements never match: the pattern anchors at the
    start and requires an imperative verb.
    """
    return bool(_INSTR_LEAD.match(text or ""))
