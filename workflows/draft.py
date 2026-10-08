"""Draft workflow: assemble a filing draft ONLY from verified claims.

For each required template field:
- typically_found_in == "user_input": take provided_values when present
  (rendered as [USER-PROVIDED: field=value], never as a claim); else
  MissingInfo.
- otherwise: retrieve inside doc_ids with the field's retrieval_query
  (fallback: name + description), run the normal claims -> verify
  pipeline, and mark the field sourced only if >=1 claim verifies; else
  MissingInfo with why_needed (template description) and searched_in.

Legal-grounds fields (names containing "provision" or "grounds") are
retrieved from doc_ids PLUS statute/judgment docs; section numbers reach
the draft only inside verified claim text — never written from memory.

precheck=True returns an Answer with status text (no draft text), the
sourced claims, the missing_info list, and confidence = sourced/required.
"""

import json
import os
import re
import time
from pathlib import Path

from contracts.schemas import Answer, Citation, Claim, MissingInfo
from verify import flags as vflags
from verify.citations import build_citations
from workflows._ground import renumber_claims, verified_only
from workflows.answer import REFUSAL, answer_from_chunks

TEMPLATES_ENV = "TEMPLATES_DIR"
_DRAFT_TYPE_RE = re.compile(r"[A-Za-z0-9_]+")

# Field names treated as legal grounds: retrieved beyond the case set,
# from statute + judgment docs as well.
_LEGAL_GROUND_HITS = ("provision", "grounds")


def _templates_dir() -> Path:
    """Template search path: $TEMPLATES_DIR, core templates/, main-tree copy.

    Templates are user3-owned content; core reads them, never writes them.
    Tests point $TEMPLATES_DIR at fixtures so the suite stays hermetic.
    """
    env = os.getenv(TEMPLATES_ENV)
    if env:
        return Path(env)
    core = Path(__file__).resolve().parent.parent / "templates"
    if core.is_dir():
        return core
    return Path("/home/frost/legal-agent/templates")


def load_template(draft_type: str) -> dict:
    """Load and shape-check templates/<draft_type>.json."""
    if not _DRAFT_TYPE_RE.fullmatch(draft_type or ""):
        raise ValueError(f"bad draft_type: {draft_type!r}")
    path = _templates_dir() / f"{draft_type}.json"
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        raise ValueError(f"unknown draft_type: {draft_type!r}")
    except json.JSONDecodeError as e:
        raise ValueError(f"template {draft_type!r} is not valid JSON: {e}")
    if not isinstance(raw.get("required_fields"), list) or not isinstance(
        raw.get("boilerplate_structure"), list
    ):
        raise ValueError(f"template {draft_type!r} lacks required_fields/boilerplate_structure")
    return raw


def _is_legal_ground(name: str) -> bool:
    return any(hit in name.casefold() for hit in _LEGAL_GROUND_HITS)


def _field_query(field: dict) -> str:
    # Templates may carry an explicit retrieval_query; otherwise fall back
    # to name + description (never model memory).
    return field.get("retrieval_query") or f"{field['name']} {field.get('description', '')}"


def run_draft(
    *,
    draft_type: str,
    doc_ids: list[str] | None,
    instructions: str | None = None,
    provided_values: dict | None = None,
    registry,
    llm,
    flagset: dict[str, bool] | None = None,
    precheck: bool = False,
    top_k: int = 4,
) -> Answer:
    """Assemble (or precheck) a draft for draft_type over doc_ids."""
    t0 = time.perf_counter()
    template = load_template(draft_type)
    doc_ids = list(doc_ids or [])
    provided_values = dict(provided_values or {})
    flagset = flagset if flagset is not None else vflags.all_flags()

    required = [f for f in template["required_fields"] if f.get("required", True)]
    law_pool = [d for d, doc in registry.docs.items() if doc.doc_type in ("statute", "judgment")]

    sourced: dict[str, list[Claim]] = {}
    user_fills: dict[str, str] = {}
    missing: list[MissingInfo] = []
    failed_total = 0

    for field in required:
        name = field["name"]
        desc = field.get("description", name)
        if field.get("typically_found_in") == "user_input":
            if name in provided_values and str(provided_values[name]).strip():
                user_fills[name] = str(provided_values[name])
            else:
                missing.append(MissingInfo(field=name, why_needed=desc, searched_in=list(doc_ids)))
            continue
        scope = list(doc_ids)
        if _is_legal_ground(name):
            scope = sorted(set(scope) | set(law_pool))
        query = _field_query(field)
        retrieved = registry.search(query, top_k=top_k, doc_ids=scope or None)
        ans = answer_from_chunks(query, "draft", registry, llm, retrieved, flagset=flagset)
        good = verified_only(ans.claims)
        failed_total += len(ans.claims) - len(good)
        if good:
            sourced[name] = good
        else:
            missing.append(MissingInfo(field=name, why_needed=desc, searched_in=scope))

    # Optional user_input fields that were provided ride along (marked, uncounted).
    for field in template["required_fields"]:
        name = field["name"]
        if (
            not field.get("required", True)
            and field.get("typically_found_in") == "user_input"
            and name not in user_fills
            and name in provided_values
            and str(provided_values[name]).strip()
        ):
            user_fills[name] = str(provided_values[name])

    # Global claim numbering (per-field pipelines each start at c1).
    ordered: list[Claim] = []
    for field in required:
        ordered.extend(sourced.get(field["name"], []))
    claims = renumber_claims(ordered)
    per_field: dict[str, list[Claim]] = {}
    it = iter(claims)
    for field in required:
        per_field[field["name"]] = [next(it) for _ in sourced.get(field["name"], [])]

    n_required = len(required)
    n_sourced = len(sourced)
    confidence = (n_sourced / n_required) if n_required else None
    ms = int((time.perf_counter() - t0) * 1000)
    chunk_map = {cid: registry.chunks[cid] for c in claims for cid in c.chunk_ids if cid in registry.chunks}
    citations: list[Citation] = build_citations(claims, chunk_map, registry.docs)
    trace = {
        "draft_type": draft_type,
        "doc_ids": doc_ids,
        "instructions": instructions,
        "sourced_fields": sorted(sourced),
        "user_fields": sorted(user_fills),
        "missing_fields": [m.field for m in missing],
        "dropped_claims": failed_total,
        "flags": dict(flagset),
        "latency_ms": ms,
    }

    if precheck:
        lines = [
            f"Precheck for {draft_type}: {n_sourced}/{n_required} required fields sourced.",
        ]
        for m in missing:
            lines.append(f"- missing {m.field}: {m.why_needed}")
        return Answer(
            workflow="draft",
            text="\n".join(lines),
            claims=claims,
            citations=citations,
            missing_info=missing,
            contradictions=[],
            confidence=confidence,
            refused=False,
            trace=trace,
        )

    if n_sourced == 0 and not user_fills:
        return Answer(
            workflow="draft",
            text=REFUSAL,
            claims=[],
            citations=[],
            missing_info=missing,
            contradictions=[],
            confidence=confidence,
            refused=True,
            refusal_reason="no field could be sourced from the provided documents",
            trace=trace,
        )

    def _fill(placeholder: str) -> str:
        if placeholder in per_field and per_field[placeholder]:
            return "; ".join(f"{c.text} [{c.claim_id}]" for c in per_field[placeholder])
        if placeholder in user_fills:
            return f"[USER-PROVIDED: {placeholder}={user_fills[placeholder]}]"
        return f"[MISSING: {placeholder}]"

    parts = [str(template.get("title", draft_type)), ""]
    for section in sorted(template["boilerplate_structure"], key=lambda s: s.get("order", 0)):
        parts.append(f"## {section.get('section', 'section')}")
        fixed = str(section.get("fixed_text", ""))
        parts.append(_render_fixed(fixed, section.get("placeholders", []), _fill))
        parts.append("")
    parts.append("Sources:")
    for c in claims:
        parts.append(f"[{c.claim_id}] {', '.join(c.chunk_ids)}: \"{c.quote}\"")
    return Answer(
        workflow="draft",
        text="\n".join(parts),
        claims=claims,
        citations=citations,
        missing_info=missing,
        contradictions=[],
        confidence=confidence,
        refused=False,
        trace=trace,
    )


def _render_fixed(fixed: str, placeholders: list[str], fill) -> str:
    """Substitute {field} placeholders; unknown ones stay literal (template bug, not our guess)."""
    out = fixed
    for p in placeholders:
        out = out.replace("{" + p + "}", fill(p))
    return out
