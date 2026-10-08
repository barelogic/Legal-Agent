"""Ablation ladder on the dev split with the live LLM (P1 flags).

Cumulative steps (each adds exactly one stage; top_k fixed at 4 for clean
attribution — the shipped top-5 baseline rides along as reference):

  L0 plain_lexical      free text, lexical top-k, no claims/verifier
  L1 +hybrid            free text, hybrid (BM25, no dense here) top-k
  L2 +rerank            L1 + cross-encoder rerank cut (RERANK_MIN_SCORE)
  L3 +relevance gate    L2 + MIN_COVERAGE on the BM25 leg
  L4 +structured        L3 retrieval + structured claims, verification SKIPPED
  L5 +verify_quote      L4 + verbatim-quote check (always-on core stage)
  L6 +verify_text       L5 + claim-text-vs-quote item check (VERIFY_TEXT)
  L7 +entailment        L6 + LLM entailment judge (VERIFY_ENTAILMENT)
  L8 +citation_gate     L7 + citation gate (VERIFY_CITATION_GATE) = full pipe

Flag control is explicit per step (no env dependence at run time except the
threshold VALUES MIN_COVERAGE/RERANK_MIN_SCORE, which are logged). SHORT
BOOST (top_k widening for <=6-token queries) is ON for L4..L8 (production
parity) and OFF for L0..L3 (plain convention is a fixed net); both logged
per answer in trace["top_k_effective"]. Regenerate is OFF throughout so the
guardrail deltas are not confounded by retry (production has it ON).

Outputs (eval/results/):
  ladder.json  per-step metrics + env/flags snapshot (one-command repro)
  ladder.md    one table: groundedness %, fab count, recall@k, refusal R
  ladder.svg   chart of the same four series across L0..L8 (no deps)
  compare.jsonl  I4 side-by-side per query: ours (L8) vs baseline_plain_rag
    (shipped, top-5, env gates) with the baseline's unsupported claims.

Re-run: .venv/bin/python eval/ladder.py [--top-k 4] [--limit N]
Suite stays mock-pinned (LLM_PROVIDER=mock override in tests); this script
uses whatever provider .env points at (live Ollama for reported numbers).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contracts.schemas import Answer

STEPS: list[dict] = [
    {"id": "L0_plain_lexical", "adds": "plain free-text baseline",
     "kind": "plain", "retrieval": "lexical",
     "coverage": 0.0, "rerank": float("-inf")},
    {"id": "L1_hybrid", "adds": "+ hybrid retrieval",
     "kind": "plain", "retrieval": "hybrid",
     "coverage": 0.0, "rerank": float("-inf")},
    {"id": "L2_rerank", "adds": "+ rerank",
     "kind": "plain", "retrieval": "hybrid",
     "coverage": 0.0, "rerank": None},
    {"id": "L3_relevance_gate", "adds": "+ relevance gate",
     "kind": "plain", "retrieval": "hybrid",
     "coverage": None, "rerank": None},
    {"id": "L4_structured_noverify", "adds": "+ structured claims (verifiers off)",
     "kind": "struct", "retrieval": "hybrid",
     "coverage": None, "rerank": None, "verify": {}},
    {"id": "L5_verify_quote", "adds": "+ verify_quote",
     "kind": "struct", "retrieval": "hybrid", "coverage": None, "rerank": None,
     "verify": {"verify_text": False, "entailment": False,
                "citation_gate": False, "regenerate": False}},
    {"id": "L6_verify_text", "adds": "+ verify_text",
     "kind": "struct", "retrieval": "hybrid", "coverage": None, "rerank": None,
     "verify": {"verify_text": True, "entailment": False,
                "citation_gate": False, "regenerate": False}},
    {"id": "L7_entailment", "adds": "+ entailment",
     "kind": "struct", "retrieval": "hybrid", "coverage": None, "rerank": None,
     "verify": {"verify_text": True, "entailment": True,
                "citation_gate": False, "regenerate": False}},
    {"id": "L8_citation_gate", "adds": "+ citation_gate (full)",
     "kind": "struct", "retrieval": "hybrid", "coverage": None, "rerank": None,
     "verify": {"verify_text": True, "entailment": True,
                "citation_gate": True, "regenerate": False}},
]

SHORT_QUERY_TOKENS = 6
SHORT_QUERY_TOP_K = 8


def _content_tokens(s: str) -> set[str]:
    import re

    return {t for t in re.findall(r"[a-z0-9]+", s.lower())} - {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
        "from", "has", "have", "in", "is", "it", "its", "of", "on", "or",
        "that", "the", "to", "was", "were", "will", "with"}


def run_plain_step(step: dict, question: str, docs: dict, chunks: dict,
                   reg, hidx, top_k: int, workflow: str = "chat") -> Answer:
    """Free-text answer (no claims/verifier) under explicit retrieval gates."""
    from eval.plain_rag import (complete_answer_text, evaluate_plain_answer,
                                parse_plain_citations, pipeline_info,
                                build_plain_rag_prompt)
    from workflows.answer import REFUSAL

    t0 = time.perf_counter()
    provider, model = pipeline_info()
    if step["retrieval"] == "lexical":
        retrieved = reg.search(question, top_k=top_k,
                               min_coverage=step["coverage"])
        backend = "ladder-lexical"
    else:
        hits = hidx.retrieve(question, top_k=top_k,
                             min_coverage=step["coverage"],
                             rerank_min_score=step["rerank"])
        retrieved = [c for c, _ in hits]
        backend = "ladder-hybrid"
    if not retrieved:
        ms = int((time.perf_counter() - t0) * 1000)
        return Answer(workflow=workflow, text=REFUSAL, claims=[],  # type: ignore[arg-type]
                      citations=[], refused=True,
                      refusal_reason="no retrieved chunks",
                      trace={"retrieved_chunk_ids": [], "backend": backend,
                             "latency_ms": ms, "top_k": top_k,
                             "top_k_effective": top_k,
                             "llm": f"{provider}:{model}",
                             "ladder_step": step["id"], "unverified": True,
                             "plain_rag_eval": {
                                 "refused": True, "n_claims": 0,
                                 "n_claims_raw": 0, "n_supported": 0,
                                 "groundedness": 1.0,
                                 "unresolved_citations": 0,
                                 "fabrication": False, "claims": [],
                                 "supported": [], "extract_mode": "none(refused)",
                                 "judge_mode": "none(refused)"}})
    prompt = build_plain_rag_prompt(question, retrieved)
    text, llm_mode = complete_answer_text(prompt, question, retrieved)
    if not text.strip():
        text = REFUSAL
    citations = parse_plain_citations(text, docs, retrieved)
    ms = int((time.perf_counter() - t0) * 1000)
    refused = text.strip() == REFUSAL
    ans = Answer(workflow=workflow, text=text, claims=[],  # type: ignore[arg-type]
                 citations=citations, refused=refused,
                 refusal_reason=None if not refused else "model declined",
                 trace={"retrieved_chunk_ids": [c.chunk_id for c in retrieved],
                        "backend": backend, "latency_ms": ms, "top_k": top_k,
                        "top_k_effective": top_k,
                        "llm": f"{provider}:{model}", "llm_mode": llm_mode,
                        "ladder_step": step["id"], "unverified": True,
                        "coverage": step["coverage"], "rerank": step["rerank"]})
    ans.trace["plain_rag_eval"] = evaluate_plain_answer(
        text, citations, retrieved, docs)
    return ans


def run_struct_step(step: dict, question: str, docs: dict, chunks: dict,
                    reg, hidx, llm, top_k: int,
                    workflow: str = "chat") -> Answer:
    """Structured-claims answer under explicit gates + verify flagset."""
    from generation.claims import generate_claims
    from generation.config import get_llm_model, get_llm_provider
    from verify.citations import build_citations
    from workflows.answer import REFUSAL, render_text

    t0 = time.perf_counter()
    eff_k = top_k
    if len(_content_tokens(question)) <= SHORT_QUERY_TOKENS:
        eff_k = max(top_k, SHORT_QUERY_TOP_K)
    hits = hidx.retrieve(question, top_k=eff_k,
                         min_coverage=step["coverage"],
                         rerank_min_score=step["rerank"])
    retrieved = [c for c, _ in hits]
    chunk_map = {c.chunk_id: c for c in retrieved}
    llm_client = f"{get_llm_provider()}:{get_llm_model()}:{type(llm).__name__}"
    flagset = {"coverage": step["coverage"] is None,
               "rerank": step["rerank"] is None, "short_boost": True,
               **(step.get("verify") or {})}
    candidates = generate_claims(llm, question, retrieved)
    if not step.get("verify"):  # L4: verifiers off — render candidates as-is
        for cl in candidates:
            cl.status = "unverified"
        citations = build_citations(candidates, chunk_map, reg.docs)
        ms = int((time.perf_counter() - t0) * 1000)
        trace = {"retrieved_chunk_ids": [c.chunk_id for c in retrieved],
                 "dropped": 0, "latency_ms": ms, "backend": "ladder-hybrid",
                 "top_k": top_k, "top_k_effective": eff_k,
                 "llm_client": llm_client, "ladder_step": step["id"],
                 "flags": flagset, "unverified": True}
        if not candidates:
            return Answer(workflow=workflow, text=REFUSAL, claims=[],  # type: ignore[arg-type]
                          citations=[], refused=True,
                          refusal_reason="no candidates (empty retrieval)",
                          trace=trace)
        return Answer(workflow=workflow, text=render_text(candidates),  # type: ignore[arg-type]
                      claims=candidates, citations=citations, refused=False,
                      trace=trace)
    from verify.judge import make_judge_client
    from verify.verifier import verify_all

    judge_client, judge_note = None, None
    if flagset.get("entailment"):
        judge_client, judge_note = make_judge_client(llm)
    verified, failed = verify_all(candidates, chunk_map, docs=reg.docs,
                                  judge=judge_client, flagset=flagset)
    citations = build_citations(verified, chunk_map, reg.docs)
    ms = int((time.perf_counter() - t0) * 1000)
    trace = {"retrieved_chunk_ids": [c.chunk_id for c in retrieved],
             "dropped": len(failed),
             "dropped_reasons": [f"{c.claim_id}: {c.verifier_note}" for c in failed],
             "fallbacks": ([judge_note] if judge_note else []),
             "latency_ms": ms, "backend": "ladder-hybrid",
             "top_k": top_k, "top_k_effective": eff_k,
             "llm_client": llm_client, "ladder_step": step["id"],
             "flags": flagset, "verify_flags": dict(step["verify"])}
    if not verified:
        reason = ("no retrieved chunk supported a verifiable claim"
                  if not retrieved else ("model returned no claims"
                                         if not candidates
                                         else "all claims failed verification"))
        return Answer(workflow=workflow, text=REFUSAL, claims=failed,  # type: ignore[arg-type]
                      citations=[], refused=True, refusal_reason=reason,
                      trace=trace)
    return Answer(workflow=workflow, text=render_text(verified),  # type: ignore[arg-type]
                  claims=verified, citations=citations, refused=False,
                  trace=trace)


def ladder_retrieval(rows: list[dict],
                     answers_by_system: dict[str, list[Answer]]) -> dict:
    """hit/recall@k/MRR from each answer's ACTUAL retrieved ids (trace)."""
    out: dict = {}
    answerable = [(r, i) for i, r in enumerate(rows) if r.get("answerable")]
    for sys, answers in answers_by_system.items():
        k = answers[0].trace.get("top_k_effective", answers[0].trace.get("top_k", 4)) \
            if answers else 4
        hits = recalls = rr = 0.0
        for r, i in answerable:
            gold = set(r.get("gold_chunk_ids", []))
            ranked = (answers[i].trace or {}).get("retrieved_chunk_ids", [])
            inter = gold & set(ranked)
            if inter:
                hits += 1
            recalls += len(inter) / max(1, len(gold))
            best = min(([ranked.index(g) + 1 for g in inter] or [0]))
            rr += 1.0 / best if best else 0.0
        n = max(1, len(answerable))
        out[sys] = {"n": len(answerable), "top_k": k,
                    "hit_rate": hits / n, "recall@k": recalls / n,
                    "mrr": rr / n}
    return out


def render_ladder_table(m: dict) -> str:
    order = ["baseline_plain_rag"] + [s["id"] for s in STEPS]
    L = ["# Ladder (dev split, live LLM, P1 flags)",
         f"pipeline: {m['pipeline_llm']} | judge: {m['judge_model']} "
         f"({m.get('judge_mode', '?')}) | top_k={m['top_k']} "
         f"| MIN_COVERAGE={m['env']['MIN_COVERAGE']} "
         f"RERANK_MIN_SCORE={m['env']['RERANK_MIN_SCORE']} "
         f"LLM_JUDGE_MODEL={m['env']['LLM_JUDGE_MODEL']}",
         f"n={m['n']} ({m['n_answerable']} answerable, {m['n_traps']} traps). "
         "groundedness = verified_rate (struct) / mean atomic-claim support (plain).",
         "",
         "| step | groundedness | fab_count | recall@k | trap_ref_R | refusal_R | use/5 | lat_ms |",
         "|---|---|---|---|---|---|---|---|"]
    for s in order:
        g = m["groundedness"].get(s, {})
        r = m["retrieval"].get(s, {})
        j = m["judge"].get(s, {})
        gr = (f"{g.get('groundedness', float('nan')):.3f}" if "groundedness" in g
              else f"{g.get('verified_rate', float('nan')):.3f}*")
        L.append(f"| {s} | {gr} | {g.get('fabrication_count', '?')} | "
                 f"{r.get('recall@k', float('nan')):.3f} | "
                 f"{g.get('trap_refusal_recall', float('nan')):.3f} | "
                 f"{g.get('refusal_recall', float('nan')):.3f} | "
                 f"{j.get('usefulness_mean', float('nan')):.3f} | "
                 f"{g.get('latency_ms_mean') or 0:.0f} |")
    L.append("*verified_rate (share of answerables with >=1 surviving claim).")
    return "\n".join(L)


def render_ladder_svg(m: dict, path: Path) -> None:
    """Dependency-free SVG: groundedness, recall@k, trap_ref_R across steps."""
    order = [s["id"] for s in STEPS]
    short = [s.split("_", 1)[0] for s in order]  # L0..L8
    series = {}
    for key, fn in (("groundedness",
                     lambda s: m["groundedness"][s].get("groundedness",
                         m["groundedness"][s].get("verified_rate", 0)) or 0),
                    ("recall@k", lambda s: m["retrieval"][s]["recall@k"]),
                    ("trap_ref_R",
                     lambda s: m["groundedness"][s]["trap_refusal_recall"])):
        series[key] = [float(fn(s)) for s in order]
    W, H, P = 640, 320, 44
    colors = {"groundedness": "#1f77b4", "recall@k": "#2ca02c",
              "trap_ref_R": "#d62728"}
    x = lambda i: P + i * (W - 2 * P) / max(1, len(order) - 1)
    y = lambda v: H - P - max(0.0, min(1.0, v)) * (H - 2 * P)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" '
             f'height="{H}" font-family="sans-serif">',
             f'<text x="{W//2}" y="22" text-anchor="middle" font-size="14">'
             "ladder: groundedness / recall@k / trap_ref_R</text>"]
    for gv in (0.0, 0.5, 1.0):
        parts.append(f'<line x1="{P}" y1="{y(gv):.0f}" x2="{W-P}" '
                     f'y2="{y(gv):.0f}" stroke="#ddd"/>')
        parts.append(f'<text x="{P-6}" y="{y(gv)+4:.0f}" text-anchor="end" '
                     f'font-size="10">{gv:.1f}</text>')
    for i, s in enumerate(short):
        parts.append(f'<text x="{x(i):.0f}" y="{H-P+16}" text-anchor="middle" '
                     f'font-size="10">{s}</text>')
    for name, vals in series.items():
        pts = " ".join(f"{x(i):.0f},{y(v):.0f}" for i, v in enumerate(vals))
        parts.append(f'<polyline points="{pts}" fill="none" '
                     f'stroke="{colors[name]}" stroke-width="2"/>')
        for i, v in enumerate(vals):
            parts.append(f'<circle cx="{x(i):.0f}" cy="{y(v):.0f}" r="3" '
                         f'fill="{colors[name]}"/>')
    lx = W - P - 130
    for j, name in enumerate(series):
        parts.append(f'<rect x="{lx}" y="{P+j*18}" width="10" height="10" '
                     f'fill="{colors[name]}"/>')
        parts.append(f'<text x="{lx+14}" y="{P+9+j*18}" font-size="11">{name}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_compare_jsonl(rows: list[dict], ours: list[Answer],
                        base: list[Answer], docs: dict, chunks: dict,
                        path: Path) -> int:
    """I4 side-by-side v1: one line per query.

    {qid, question, answerable, trap, ours: {system, text, refused,
      claims: [{text, quote, chunk_ids, status}], citations, latency_ms},
     baseline: {system, text, refused, atomic_claims, supported,
      unsupported_claims, unresolved_citations, groundedness},
     delta: {ours_refused, baseline_refused, baseline_fab}}
    unsupported_claims = atomic claims judged NOT_SUPPORTED (or all raw
    claims when extraction failed on an answered row) — the P3 evidence.
    """
    from eval.plain_rag import evaluate_plain_answer

    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for r, o, b in zip(rows, ours, base):
            ev = (b.trace or {}).get("plain_rag_eval")
            if not isinstance(ev, dict) or "fabrication" not in ev:
                cids = (b.trace or {}).get("retrieved_chunk_ids", [])
                retr = [chunks[c] for c in cids if c in chunks]
                ev = evaluate_plain_answer(b.text, list(b.citations), retr, docs)
            claims = ev.get("claims", [])
            flags = ev.get("supported", [])
            unsup = [c for c, ok in zip(claims, flags) if not ok]
            if b.refused:
                unsup = []
            elif not claims and b.text.strip():
                unsup = ["(no atomic claims extracted from answered text)"]
            line = {
                "qid": r.get("qid"), "question": r.get("question"),
                "answerable": bool(r.get("answerable")),
                "trap": bool(r.get("trap")),
                "ours": {
                    "system": "L8_citation_gate",
                    "text": o.text, "refused": o.refused,
                    "claims": [{"text": c.text, "quote": c.quote,
                                "chunk_ids": c.chunk_ids, "status": c.status}
                               for c in o.claims],
                    "citations": [c.model_dump() for c in o.citations],
                    "latency_ms": (o.trace or {}).get("latency_ms")},
                "baseline": {
                    "system": "baseline_plain_rag",
                    "text": b.text, "refused": b.refused,
                    "atomic_claims": claims, "supported": [bool(x) for x in flags],
                    "unsupported_claims": unsup,
                    "unresolved_citations": ev.get("unresolved_citations", 0),
                    "groundedness": ev.get("groundedness")},
                "delta": {"ours_refused": o.refused,
                          "baseline_refused": b.refused,
                          "baseline_fab": bool(ev.get("fabrication"))}}
            f.write(json.dumps(line) + "\n")
            n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="P1-flags ladder on dev split")
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0,
                    help="cap dev rows (smoke test); 0 = all")
    ap.add_argument("--out", default="eval/results")
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    out = root / args.out
    out.mkdir(parents=True, exist_ok=True)

    from eval.score_queries import load_resolved, try_load_processed_corpus
    from eval.systems import make_registry, run_system
    from generation.config import get_llm_model, get_llm_provider
    from generation.llm import make_client
    from eval.judge import get_judge_model, judge_answers
    from eval.metrics_grounded import groundedness_report

    docs, chunks = try_load_processed_corpus()
    if not docs or not chunks:
        print("no data/processed/; run corpus/build_corpus.py first")
        return 2
    rows = load_resolved(holdout=False)
    if args.limit:
        rows = rows[:args.limit]

    reg = make_registry(docs, chunks)
    from retrieval.hybrid import HybridIndex

    hidx = HybridIndex(list(chunks.values()))
    llm = make_client()

    order = ["baseline_plain_rag"] + [s["id"] for s in STEPS]
    answers: dict[str, list[Answer]] = {}

    def _safe(fn, *a, **k) -> Answer:
        """One slow/failed LLM call must not kill a multi-hour live run."""
        from workflows.answer import REFUSAL

        try:
            return fn(*a, **k)
        except Exception as e:  # noqa: BLE001 — recorded, never swallowed
            q = a[1] if len(a) > 1 else "?"
            print(f"  ladder-error ({e.__class__.__name__}): {str(q)[:60]}",
                  flush=True)
            return Answer(workflow="chat", text=REFUSAL, claims=[],
                          citations=[], refused=True,
                          refusal_reason=f"ladder-error:{e.__class__.__name__}",
                          trace={"retrieved_chunk_ids": [],
                                 "latency_ms": None, "ladder_error": str(e)[:200]})

    t_all = time.time()
    answers["baseline_plain_rag"] = [
        _safe(run_system, "baseline_plain_rag", r["question"], docs, chunks,
              top_k=5, workflow=r.get("workflow", "chat")) for r in rows]
    print(f"baseline_plain_rag done ({time.time()-t_all:.0f}s)", flush=True)
    for s in STEPS:
        t0 = time.time()
        col = []
        for r in rows:
            if s["kind"] == "plain":
                col.append(_safe(run_plain_step, s, r["question"], docs, chunks,
                                 reg, hidx, args.top_k,
                                 workflow=r.get("workflow", "chat")))
            else:
                col.append(_safe(run_struct_step, s, r["question"], docs, chunks,
                                  reg, hidx, llm, args.top_k,
                                  workflow=r.get("workflow", "chat")))
        answers[s["id"]] = col
        print(f"{s['id']} done ({time.time()-t0:.0f}s)", flush=True)

    retrieval = ladder_retrieval(rows, answers)
    grounded = groundedness_report(answers, rows, docs, chunks)
    try:
        judge = judge_answers(answers, rows)
        judge_mode = judge.get("judge_mode", "?")
    except ValueError as e:
        judge = {"error": str(e), "judge_model": "mismatch-blocked"}
        judge_mode = "mismatch-blocked"
    from generation.config import get_min_coverage, get_rerank_min_score

    m = {"pipeline_llm": f"{get_llm_provider()}:{get_llm_model()}",
         "judge_model": judge.get("judge_model", "?"),
         "judge_mode": judge_mode,
         "top_k": args.top_k, "n": len(rows),
         "n_answerable": sum(1 for r in rows if r.get("answerable")),
         "n_traps": sum(1 for r in rows if r.get("trap")),
         "env": {"MIN_COVERAGE": os.getenv("MIN_COVERAGE", "0.32"),
                 "RERANK_MIN_SCORE": os.getenv("RERANK_MIN_SCORE", "0.0"),
                 "LLM_JUDGE_MODEL": os.getenv("LLM_JUDGE_MODEL", ""),
                 "eff_MIN_COVERAGE": get_min_coverage(),
                 "eff_RERANK_MIN_SCORE": get_rerank_min_score()},
         "steps": STEPS, "retrieval": retrieval,
         "groundedness": grounded, "judge": judge,
         "elapsed_s": round(time.time() - t_all)}
    (out / "ladder.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
    table = render_ladder_table(m)
    (out / "ladder.md").write_text(table + "\n", encoding="utf-8")
    render_ladder_svg(m, out / "ladder.svg")
    n_cmp = write_compare_jsonl(
        rows, answers["L8_citation_gate"],
        answers["baseline_plain_rag"], docs, chunks, out / "compare.jsonl")
    print(table)
    print(f"\nwrote ladder.json/ladder.md/ladder.svg + compare.jsonl ({n_cmp} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
