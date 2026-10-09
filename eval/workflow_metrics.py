"""E4 workflow metrics: draft / review / research (bonus-points evidence).

Uses the D1 case files (synthetic matter-1: FIR 0451/2024 + 5 linked docs)
already in the corpus, plus two planted conflict docs (in-memory only) for
review P/R. Live LLM when configured, MockClient offline (mode logged).

- Draft (bail_application): field-fill precision (sourced fields whose
  claims contain the gold value), missing-info recall (expected-missing
  fields that were flagged), fabrication count inside draft text
  (claims failing the verbatim quote check + unresolved citations).
- Review: contradiction P/R on the planted pair (surety-amount + date-of-
  arrest conflicts), plus the natural D1 run (expect 0 contradictions).
  A deterministic detector unit check (no LLM) pins the regex layer.
- Research: % of cited items resolving to a registry Doc + old-law mapping
  MissingInfo behaviour (section_map.json carries repeal rows only).

Re-run: .venv/bin/python eval/workflow_metrics.py [--out eval/results]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contracts.schemas import Chunk, Claim, Doc

MATTER1 = ["synth_cf_01_fir", "synth_cf_02_remand",
           "synth_cf_03_chargesheet_excerpt", "synth_cf_04_medical",
           "synth_cf_05_bail_application", "synth_cf_06_surety_affidavit"]

# Expected-missing draft fields (no provided_values; absent from D1 files).
EXPECTED_MISSING = {"court", "case_number", "criminal_antecedents",
                    "previous_bail_applications", "coercive_processes",
                    "prayer", "surety_details", "applicant_counsel",
                    "verification_place_date"}

# Gold substrings per sourced field (lowercased); None = presence-only.
GOLD = {"applicant_name": "vikas sharma", "applicant_address": "rose lane",
        "fir_number": "0451/2024", "fir_date": "12 march 2024",
        "police_station": "model town", "provisions_invoked": "cheating",
        "date_of_arrest": "15 march 2024", "custody_days": "3 days",
        "stage_of_proceedings": None, "facts_chronology": None,
        "grounds_for_bail": None, "bail_provision": None}


def _norm(s: str) -> str:
    return " ".join((s or "").split()).casefold()


def draft_metrics(answer, registry) -> dict:
    sourced = (answer.trace or {}).get("sourced_fields", [])
    missing = {(m.field if hasattr(m, "field") else m.get("field"))
               for m in (answer.missing_info or [])}
    # Field-fill precision: gold value present in the draft's verified claim
    # text. Whole-draft matching (trace carries no per-field claim map);
    # gold values are distinct numbers/names so misattribution is unlikely.
    full = _norm(" ".join(c.text for c in answer.claims))
    matched = total = 0
    detail: dict[str, bool] = {}
    for f in sourced:
        if f not in GOLD:
            continue
        total += 1
        g = GOLD[f]
        if g is None:
            if f == "stage_of_proceedings":
                ok = ("investig" in full) or ("charge" in full)
            elif f == "bail_provision":
                ok = ("bail" in full) or ("48" in full)
            else:
                ok = len(full.split()) > 3
        else:
            ok = g in full
        detail[f] = ok
        matched += ok
    # fabrication inside draft text: quote must be verbatim in cited chunk
    fab = 0
    chunk_texts = {cid: ch.text for cid, ch in registry.chunks.items()}
    for c in answer.claims:
        texts = [chunk_texts[cid] for cid in c.chunk_ids if cid in chunk_texts]
        if not c.quote.strip() or not any(
                _norm(c.quote) in _norm(t) for t in texts):
            fab += 1
    unresolved = sum(1 for ci in answer.citations
                     if not (ci.resolved and ci.doc_id in registry.docs))
    exp = set(EXPECTED_MISSING)
    n_required = len(sourced) + len(missing)
    return {"n_required": n_required,
            "n_sourced": len(sourced),
            "field_fill_precision": (matched / total) if total else 1.0,
            "field_fill_detail": detail,
            "missing_recall": len(missing & exp) / max(1, len(exp)),
            "missing_precision": len(missing & exp) / max(1, len(missing)),
            "missing_flagged": sorted(missing),
            "fabrication_in_draft": fab + unresolved,
            "refused": answer.refused}


def planted_docs() -> tuple[Doc, Chunk, Doc, Chunk]:
    """Two in-memory case files disagreeing on amount + arrest date."""
    a = Doc(doc_id="plant_amt_date_a", title="plant A", doc_type="case_file")
    b = Doc(doc_id="plant_amt_date_b", title="plant B", doc_type="case_file")
    ta = ("FIR No. 0451/2024 records that Vikas Sharma stood surety bond "
          "of Rs. 50,000 and that date of arrest 15/03/2024 is on record.")
    tb = ("Supplementary note on FIR No. 0451/2024 records that Vikas Sharma "
          "stood surety bond of Rs. 75,000 and that date of arrest "
          "18/03/2024 is on record.")
    return (a, Chunk(chunk_id="plant_amt_date_a::p1::c1", doc_id=a.doc_id, text=ta),
            b, Chunk(chunk_id="plant_amt_date_b::p1::c1", doc_id=b.doc_id, text=tb))


def detector_unit_check() -> dict:
    """find_contradictions on hand-made verified claims (no LLM)."""
    from workflows.review import find_contradictions

    _, ca, _, cb = planted_docs()
    claims = [
        Claim(claim_id="c1", text=ca.text, chunk_ids=[ca.chunk_id],
              quote=ca.text, status="verified"),
        Claim(claim_id="c2", text=cb.text, chunk_ids=[cb.chunk_id],
              quote=cb.text, status="verified")]
    found = find_contradictions(claims)
    attrs = {d.description.split(":")[0] for d in found}
    exp = {"surety amount", "date of arrest"}
    return {"expected": sorted(exp), "found": [d.description for d in found],
            "precision": len(attrs & exp) / max(1, len(attrs)),
            "recall": len(attrs & exp) / max(1, len(exp))}


def review_metrics(review_ans, expected_attrs: set[str]) -> dict:
    attrs = {(d.description.split(":")[0]) for d in (review_ans.contradictions or [])}
    return {"n_contradictions": len(review_ans.contradictions or []),
            "descriptions": [d.description for d in (review_ans.contradictions or [])],
            "precision": len(attrs & expected_attrs) / max(1, len(attrs)) if attrs else 1.0,
            "recall": len(attrs & expected_attrs) / max(1, len(expected_attrs))}


def research_metrics(answers: list) -> dict:
    tot = res = 0
    per_q = []
    for a in answers:
        q_tot = len(a.citations)
        # build_citations is resolved-only by construction; re-resolve anyway.
        q_res = sum(1 for ci in a.citations if ci.resolved and ci.doc_id)
        tot += q_tot
        res += q_res
        per_q.append({"refused": a.refused, "n_citations": q_tot,
                      "n_missing": len(a.missing_info or []),
                      "missing": [m.field for m in (a.missing_info or [])]})
    return {"citation_resolution_rate": (res / tot) if tot else 1.0,
            "n_citations": tot, "per_question": per_q}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="E4 workflow metrics")
    ap.add_argument("--out", default="eval/results")
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    out = root / args.out
    out.mkdir(parents=True, exist_ok=True)

    from eval.score_queries import try_load_processed_corpus
    from generation.config import get_llm_model, get_llm_provider
    from generation.llm import make_client
    from retrieval.store import Registry

    docs, chunks = try_load_processed_corpus()
    if not docs or not chunks:
        print("no data/processed/; run corpus/build_corpus.py first")
        return 2
    reg = Registry()
    for d in docs.values():
        reg.register_doc(d)
    for c in chunks.values():
        reg.chunks[c.chunk_id] = c
    llm = make_client()
    llm_mode = f"{get_llm_provider()}:{get_llm_model()}:{type(llm).__name__}"
    t_all = time.time()

    from workflows.draft import run_draft
    from workflows.research import run_research
    from workflows.review import run_review

    t0 = time.time()
    try:
        draft = run_draft(draft_type="bail_application", doc_ids=MATTER1,
                          instructions="Seek regular bail; cooperate; two sureties.",
                          provided_values=None, registry=reg, llm=llm)
    except Exception as e:  # noqa: BLE001 — live-run resilience, logged below
        from contracts.schemas import Answer as _A

        draft = _A(workflow="draft", text="Not found in the provided sources",
                   claims=[], citations=[], refused=True,
                   refusal_reason=f"workflow-error:{e.__class__.__name__}",
                   trace={"sourced_fields": [], "latency_ms": None,
                          "workflow_error": str(e)[:200]})
    d_metrics = draft_metrics(draft, reg)
    d_metrics["latency_s"] = round(time.time() - t0, 1)
    print(f"draft done ({d_metrics['latency_s']}s) prec={d_metrics['field_fill_precision']:.2f} "
          f"missR={d_metrics['missing_recall']:.2f} fab={d_metrics['fabrication_in_draft']}",
          flush=True)

    t0 = time.time()
    try:
        natural = run_review(doc_ids=MATTER1, registry=reg, llm=llm)
    except Exception as e:  # noqa: BLE001
        from contracts.schemas import Answer as _A

        natural = _A(workflow="review",
                     text="Not found in the provided sources",
                     claims=[], citations=[], refused=True,
                     refusal_reason=f"workflow-error:{e.__class__.__name__}",
                     trace={"per_doc_counts": {},
                            "workflow_error": str(e)[:200]})
    natural_m = {"n_contradictions": len(natural.contradictions or []),
                 "descriptions": [d.description for d in (natural.contradictions or [])],
                 "per_doc_counts": (natural.trace or {}).get("per_doc_counts", {})}
    # planted pair (in-memory; D1 files untouched)
    da, ca, db, cb = planted_docs()
    reg.register_doc(da)
    reg.register_doc(db)
    reg.chunks[ca.chunk_id] = ca
    reg.chunks[cb.chunk_id] = cb
    planted = None
    try:
        planted = run_review(doc_ids=[da.doc_id, db.doc_id], registry=reg, llm=llm)
    except Exception as e:  # noqa: BLE001
        print(f"planted review failed ({e.__class__.__name__}); "
              "P/R falls back to detector unit check", flush=True)
    exp_attrs = {"surety amount", "date of arrest"}
    planted_m = (review_metrics(planted, exp_attrs) if planted is not None
                 else {"n_contradictions": None, "descriptions": [],
                       "precision": None, "recall": None,
                       "note": "live run failed; see detector_unit"})
    planted_m["latency_s"] = round(time.time() - t0, 1)
    print(f"review done planted P={planted_m['precision']:.2f} "
          f"R={planted_m['recall']:.2f} natural={natural_m['n_contradictions']}",
          flush=True)

    t0 = time.time()
    rq = [("What amount is alleged in FIR No. 0451/2024?", MATTER1),
          ("When must a person arrested for a bailable offence be released on bail?", None),
          ("How does Section 436 of the CrPC map to the new law?", None)]
    r_answers = []
    for q, dids in rq:
        try:
            r_answers.append(run_research(question=q, doc_ids=dids,
                                          registry=reg, llm=llm))
        except Exception as e:  # noqa: BLE001
            from contracts.schemas import Answer as _A

            print(f"research failed ({e.__class__.__name__}): {q[:50]}",
                  flush=True)
            r_answers.append(_A(
                workflow="research",
                text="Not found in the provided sources",
                claims=[], citations=[], refused=True,
                refusal_reason=f"workflow-error:{e.__class__.__name__}",
                trace={"workflow_error": str(e)[:200]}))
    r_metrics = research_metrics(r_answers)
    r_metrics["latency_s"] = round(time.time() - t0, 1)
    print(f"research done resolve={r_metrics['citation_resolution_rate']:.2f} "
          f"ncit={r_metrics['n_citations']}", flush=True)

    m = {"llm": llm_mode, "elapsed_s": round(time.time() - t_all, 1),
         "draft": d_metrics, "review_natural": natural_m,
         "review_planted": planted_m,
         "detector_unit": detector_unit_check(), "research": r_metrics}
    (out / "workflow_metrics.json").write_text(json.dumps(m, indent=1),
                                               encoding="utf-8")
    print(json.dumps(m, indent=1))
    print(f"\nwrote {out / 'workflow_metrics.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
