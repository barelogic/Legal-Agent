"""Research workflow: case facts -> statute/judgment law -> old-to-new map.

Takes the case-fact claims (retrieved inside the case doc_ids), retrieves
statute and judgment chunks on the same question, and connects them through
verified claims; citations resolve against the registry (unresolved ones
are dropped by construction).

When the question or the verified case claims cite an IPC / CrPC / Evidence
Act section, the mention is looked up in corpus/section_map.json. Rows in
that file are the only verified mappings: if no row matches, a MissingInfo
("no verified old-to-new mapping available") is returned — never a guess
from memory. Every mapping shown carries its source_url; a row without one
is treated as unverified.
"""

import json
import os
import re
import time
from pathlib import Path

from contracts.schemas import Answer, MissingInfo
from verify import flags as vflags
from verify.citations import build_citations
from workflows._ground import renumber_claims, verified_only
from workflows.answer import REFUSAL, answer_from_chunks, render_text

SECTION_MAP_ENV = "SECTION_MAP_PATH"

_ACT_ALIASES: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"Indian\s+Penal\s+Code|\bIPC\b", re.I), "indian penal code"),
    (re.compile(r"Code\s+of\s+Criminal\s+Procedure|\bCrPC\b|Cr\.P\.C\.", re.I),
     "code of criminal procedure"),
    (re.compile(r"Indian\s+Evidence\s+Act|Evidence\s+Act|\bIEA\b", re.I), "indian evidence act"),
)
_SECTION_RE = re.compile(r"\bSection\s*(\d+[A-Za-z]?(?:\(\d+\))?)", re.I)


def _section_map_path() -> Path:
    env = os.getenv(SECTION_MAP_ENV)
    if env:
        return Path(env)
    core = Path(__file__).resolve().parent.parent / "corpus" / "section_map.json"
    if core.is_file():
        return core
    return Path("/home/frost/legal-agent/corpus/section_map.json")


def load_section_map(path: Path | None = None) -> tuple[list[dict], Path]:
    """Load the verified old-to-new mapping file (empty rows if unreadable)."""
    p = Path(path) if path else _section_map_path()
    try:
        rows = json.loads(p.read_text()).get("rows", [])
    except (FileNotFoundError, json.JSONDecodeError):
        rows = []
    return ([r for r in rows if isinstance(r, dict)], p)


def extract_old_law_mentions(*texts: str) -> list[tuple[str, str]]:
    """(act_key, section) pairs where an old-Act name sits near a Section N.

    Attribution window is ±80 chars; a bare "Section N" with no Act nearby
    is skipped (mapping it would be a guess).
    """
    out: list[tuple[str, str]] = []
    for text in texts:
        if not text:
            continue
        for m in _SECTION_RE.finditer(text):
            sec = m.group(1)
            window = text[max(0, m.start() - 80): m.end() + 80]
            for rx, key in _ACT_ALIASES:
                if rx.search(window):
                    out.append((key, sec))
                    break
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for p in out:
        if p not in seen:
            seen.add(p)
            deduped.append(p)
    return deduped


def lookup_mapping(rows: list[dict], act_key: str, section: str) -> dict | None:
    """Find the verified row for (old act, old section), else None."""
    sec = section.strip().casefold()
    for r in rows:
        old_act = str(r.get("old_act", "")).casefold()
        old_sec = r.get("old_section")
        if old_sec is None:
            continue  # repeal rows map whole Acts, not sections
        if act_key in old_act and str(old_sec).strip().casefold() == sec:
            return r
    return None


def run_research(
    *,
    question: str,
    doc_ids: list[str] | None,
    registry,
    llm,
    flagset: dict[str, bool] | None = None,
    top_k: int = 4,
    section_map_path: Path | str | None = None,
) -> Answer:
    """Case facts + statute/judgment law + verified old-to-new mappings."""
    t0 = time.perf_counter()
    if not (question or "").strip():
        raise ValueError("question must not be empty")
    flagset = flagset if flagset is not None else vflags.all_flags()
    doc_ids = list(doc_ids or [])

    case_hits = registry.search(question, top_k=top_k, doc_ids=doc_ids or None)
    case_ans = answer_from_chunks(question, "research", registry, llm, case_hits, flagset=flagset)
    case_claims = verified_only(case_ans.claims)

    law_pool = [d for d, doc in registry.docs.items() if doc.doc_type in ("statute", "judgment")]
    law_hits = registry.search(question, top_k=top_k, doc_ids=law_pool or None)
    law_ans = answer_from_chunks(question, "research", registry, llm, law_hits, flagset=flagset)
    law_claims = verified_only(law_ans.claims)

    claims = renumber_claims(case_claims + law_claims)
    failed = [c for c in case_ans.claims + law_ans.claims if c.status != "verified"]

    rows, map_path = load_section_map(Path(section_map_path) if section_map_path else None)
    mentions = extract_old_law_mentions(question, *(c.text for c in case_claims))
    mapping_lines: list[str] = []
    missing: list[MissingInfo] = []
    for act_key, sec in mentions:
        row = lookup_mapping(rows, act_key, sec)
        url = (row or {}).get("source_url")
        if row is not None and url:
            mapping_lines.append(
                f"- {act_key.title()} Section {sec} → "
                f"{row.get('new_act')} Section {row.get('new_section')} "
                f"({row.get('relation')}; source: {url})"
            )
        else:
            missing.append(MissingInfo(
                field=f"old-to-new mapping for {act_key} Section {sec}",
                why_needed="no verified old-to-new mapping available",
                searched_in=[str(map_path)]))

    chunk_map = {cid: registry.chunks[cid] for c in claims for cid in c.chunk_ids if cid in registry.chunks}
    citations = build_citations(claims, chunk_map, registry.docs)
    total = len(claims) + len(failed)
    ms = int((time.perf_counter() - t0) * 1000)
    trace = {
        "doc_ids": doc_ids,
        "case_hits": [c.chunk_id for c in case_hits],
        "law_hits": [c.chunk_id for c in law_hits],
        "mentions": [f"{a} {s}" for a, s in mentions],
        "section_map": str(map_path),
        "flags": dict(flagset),
        "latency_ms": ms,
    }
    if not claims:
        return Answer(
            workflow="research",
            text=REFUSAL,
            claims=failed,
            citations=[],
            missing_info=missing,
            contradictions=[],
            confidence=(0.0 if total else None),
            refused=True,
            refusal_reason="no verifiable claim in case or statute/judgment sources",
            trace=trace,
        )
    text = render_text(claims)
    if mentions:
        text += "\n\nOld-to-new section mappings:\n"
        text += "\n".join(mapping_lines) if mapping_lines else ""
        if missing:
            text += ("\n" if mapping_lines else "") + "\n".join(
                f"[MISSING: {m.field} — {m.why_needed}]" for m in missing)
    else:
        text += "\n\nNo old-law section references detected."
    return Answer(
        workflow="research",
        text=text,
        claims=claims,
        citations=citations,
        missing_info=missing,
        contradictions=[],
        confidence=(len(claims) / total if total else None),
        refused=False,
        trace=trace,
    )
