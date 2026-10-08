"""One command reproduces every number in the write-up.

    .venv/bin/python eval/run_all.py [--hf-limit 50] [--top-k 4] [--gold-per-doc 2]

Steps: corpus (seeds + HF sample) -> gold -> run 3 systems -> retrieval +
groundedness + judge + ablations -> eval/results/metrics.json + tables.md.
Plus: hand-built eval/queries.jsonl (40, incl. 10 traps, 10 holdout)
resolved against data/processed/ and scored on the tunable split.
Prints the tables to stdout. Deterministic offline (MockClient + fallback
judge); live Gemini judge only when GEMINI_API_KEY is set (model logged).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.ablations import run_ablations
from eval.corpus_sources import build_corpus, corpus_registry
from eval.gold import build_gold, load_gold
from eval.judge import get_judge_model, judge_answers
from eval.metrics_grounded import groundedness_report
from eval.metrics_retrieval import retrieval_report
from eval.systems import run_system

SYSTEMS = ("full_lexical_verified", "baseline_no_verify", "hybrid_verified", "baseline_injected")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reproduce all eval numbers")
    ap.add_argument("--hf-limit", type=int, default=50)
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--gold-per-doc", type=int, default=2)
    ap.add_argument("--out", default="eval/results")
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    out = root / args.out
    out.mkdir(parents=True, exist_ok=True)

    stats = build_corpus(out_dir=root / "eval" / "datasets", hf_limit=args.hf_limit)
    docs, chunks = corpus_registry(hf_limit=args.hf_limit)
    gold_path = build_gold(chunks, out_path=root / "eval" / "datasets" / "gold.jsonl",
                           per_doc=args.gold_per_doc)
    rows = load_gold(gold_path)

    answers_by_system = {
        s: [run_system(s, r["question"], docs, chunks, top_k=args.top_k) for r in rows]
        for s in SYSTEMS
    }
    retrieval = retrieval_report(rows, docs, chunks, systems=SYSTEMS, top_k=args.top_k)
    grounded = groundedness_report(answers_by_system, rows, docs, chunks)
    try:
        judge = judge_answers(answers_by_system, rows)
    except ValueError as e:
        judge = {"error": str(e), "judge_model": "mismatch-blocked"}
    ablations = run_ablations(rows, docs, chunks)

    try:
        from eval.score_queries import load_processed_corpus, load_resolved, score_queries

        import eval.build_queries as _bq

        _bq.main([])
        pdocs, pchunks = load_processed_corpus()
        queries = score_queries(pdocs, pchunks, top_k=args.top_k)
        queries["holdout_qids"] = [r["qid"] for r in load_resolved(holdout=True)]
    except Exception as e:
        queries = {"error": f"{e.__class__.__name__}: {e}"}

    try:
        judge_model = judge.get("judge_model", "unknown")
    except AttributeError:
        judge_model = "unknown"
    metrics = {
        "corpus": {
            "num_docs": stats.num_docs,
            "num_chunks": stats.num_chunks,
            "num_real_with_source_url": stats.num_real,
            "num_demo_without_source_url": stats.num_demo,
            "hf_limit": args.hf_limit,
        },
        "gold": {"n": len(rows), "answerable": sum(1 for r in rows if r.get("answerable"))},
        "pipeline_llm": __import__("os").getenv("LLM_MODEL", "gemini-2.0-flash"),
        "judge_model": get_judge_model() if "error" not in judge else judge_model,
        "top_k": args.top_k,
        "retrieval": retrieval,
        "groundedness": grounded,
        "judge": judge,
        "ablations": ablations,
        "queries": queries,
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    tables = render_tables(metrics)
    (out / "tables.md").write_text(tables, encoding="utf-8")
    print(tables)
    print(f"\nwrote {out / 'metrics.json'} and {out / 'tables.md'}")
    return 0


def render_tables(m: dict) -> str:
    L: list[str] = []
    L.append(f"# Eval results (judge: {m['judge_model']} vs pipeline: {m['pipeline_llm']})")
    c = m["corpus"]
    L.append(f"Corpus: {c['num_docs']} docs / {c['num_chunks']} chunks "
             f"({c['num_real_with_source_url']} real with source_url, "
             f"{c['num_demo_without_source_url']} demo). "
             f"Gold: {m['gold']['n']} ({m['gold']['answerable']} answerable).")
    L.append("\n## Retrieval (answerable only)")
    L.append("| system | hit_rate | recall@k | mrr |")
    L.append("|---|---|---|---|")
    for s, r in m["retrieval"].items():
        if isinstance(r, dict) and "hit_rate" in r:
            L.append(f"| {s} | {r['hit_rate']:.3f} | {r['recall@k']:.3f} | {r['mrr']:.3f} |")
    L.append("\n## Groundedness")
    L.append("| system | verified_rate | cite_resolved | refusal_R | fabrication |")
    L.append("|---|---|---|---|---|")
    for s, g in m["groundedness"].items():
        L.append(f"| {s} | {g['verified_rate']:.3f} | {g['citation_resolved_rate']:.3f} "
                 f"| {g['refusal_recall']:.3f} | {g['fabrication_rate']:.3f} |")
    L.append("\n## Judge (usefulness / entailment)")
    j = m["judge"]
    L.append(f"mode: {j.get('judge_mode', '?')}")
    L.append("| system | usefulness | entailment |")
    L.append("|---|---|---|")
    for s, v in j.items():
        if isinstance(v, dict) and "usefulness_mean" in v:
            L.append(f"| {s} | {v['usefulness_mean']:.3f} | {v['entailment_rate']:.3f} |")
    L.append("\n## Ablations")
    for name, a in m["ablations"].items():
        if isinstance(a, dict) and "retrieval" in a:
            L.append(f"- {name}: recall={a['retrieval']['recall@k']:.3f} "
                     f"fab={a['groundedness']['fabrication_rate']:.3f}")
        else:
            L.append(f"- {name}: {a}")
    L.append("\n## Hand-built queries (tunable split; holdout excluded)")
    q = m.get("queries", {})
    if "error" in q:
        L.append(f"queries section failed: {q['error']}")
    else:
        L.append(f"n={q['n']} ({q['n_answerable']} answerable), "
                 f"holdout=[{', '.join(q.get('holdout_qids', []))}]")
        L.append("| system | hit_rate | recall@k | verified | refusal_R | fabrication |")
        L.append("|---|---|---|---|---|---|")
        for s in ("full_lexical_verified", "baseline_no_verify", "hybrid_verified",
                  "baseline_injected"):
            r = q["retrieval"].get(s, {})
            g = q["groundedness"].get(s, {})
            L.append(f"| {s} | {r.get('hit_rate', float('nan')):.3f} | "
                     f"{r.get('recall@k', float('nan')):.3f} | "
                     f"{g.get('verified_rate', float('nan')):.3f} | "
                     f"{g.get('refusal_recall', float('nan')):.3f} | "
                     f"{g.get('fabrication_rate', float('nan')):.3f} |")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
