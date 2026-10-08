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

SYSTEMS = ("full_lexical_verified", "baseline_no_verify", "hybrid_verified",
           "baseline_injected", "baseline_plain_rag")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reproduce all eval numbers")
    ap.add_argument("--hf-limit", type=int, default=50)
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--gold-per-doc", type=int, default=2)
    ap.add_argument("--gold-max-docs", type=int, default=30)
    ap.add_argument("--corpus", default="auto",
                    choices=("auto", "registry", "processed"),
                    help="auto (default): data/processed/ when built, else "
                         "seeds+HF registry. One corpus feeds gold AND the "
                         "queries split so metrics.json is comparable.")
    ap.add_argument("--rebuild-queries", action="store_true",
                    help="force rebuild of queries_resolved.jsonl (default: "
                         "rebuild only when missing or older than "
                         "data/processed/docs.jsonl)")
    ap.add_argument("--out", default="eval/results")
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    out = root / args.out
    out.mkdir(parents=True, exist_ok=True)

    from eval.score_queries import try_load_processed_corpus

    pdocs, pchunks = try_load_processed_corpus()
    use_processed = (args.corpus == "processed" or
                     (args.corpus == "auto" and bool(pdocs and pchunks)))
    if args.corpus == "processed" and not (pdocs and pchunks):
        print("no data/processed/; run corpus/build_corpus.py first")
        return 2
    if use_processed:
        docs, chunks = pdocs, pchunks
        corpus_source = "processed(data/processed/)"
        stats = None
    else:
        stats = build_corpus(out_dir=root / "eval" / "datasets", hf_limit=args.hf_limit)
        docs, chunks = corpus_registry(hf_limit=args.hf_limit)
        corpus_source = f"registry(seeds+hf_limit={args.hf_limit})"
    gold_path = build_gold(chunks, out_path=root / "eval" / "datasets" / "gold.jsonl",
                           per_doc=args.gold_per_doc, max_docs=args.gold_max_docs)
    rows = load_gold(gold_path)

    answers_by_system = {
        s: [run_system(s, r["question"], docs, chunks, top_k=args.top_k,
                       workflow=r.get("workflow", "chat")) for r in rows]
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
        from eval.score_queries import load_resolved, score_queries

        import eval.build_queries as _bq

        if not (pdocs and pchunks):
            queries = {"skipped": "no data/processed/; queries split needs "
                                  "corpus/build_corpus.py output"}
        else:
            resolved_p = root / "eval" / "datasets" / "queries_resolved.jsonl"
            docs_p = root / "data" / "processed" / "docs.jsonl"
            stale = (not resolved_p.is_file() or
                     (docs_p.is_file() and
                      docs_p.stat().st_mtime > resolved_p.stat().st_mtime))
            if args.rebuild_queries or stale:
                _bq.main([])
            queries = score_queries(pdocs, pchunks, top_k=args.top_k)
            queries["holdout_qids"] = [r["qid"] for r in load_resolved(holdout=True)]
    except Exception as e:
        queries = {"error": f"{e.__class__.__name__}: {e}"}

    try:
        judge_model = judge.get("judge_model", "unknown")
    except AttributeError:
        judge_model = "unknown"
    from generation.config import get_llm_model as _glm, get_llm_provider as _glp
    plain_modes = set()
    for ans in answers_by_system.get("baseline_plain_rag", []):
        mm = (ans.trace or {}).get("llm_mode")
        if mm:
            plain_modes.add(str(mm).split("(")[0])
    n_real = sum(1 for d in docs.values() if getattr(d, "source_url", None))
    metrics = {
        "corpus": {
            "source": corpus_source,
            "num_docs": len(docs),
            "num_chunks": len(chunks),
            "num_real_with_source_url": n_real,
            "num_demo_without_source_url": len(docs) - n_real,
            "hf_limit": args.hf_limit,
        },
        "gold": {"n": len(rows), "answerable": sum(1 for r in rows if r.get("answerable"))},
        "pipeline_llm": _glm(),
        "pipeline_provider": _glp(),
        "plain_rag_llm_mode": "+".join(sorted(plain_modes)) or "n/a",
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


def _label(s: str) -> str:
    return f"{s} (synthetic)" if s == "baseline_injected" else s


def _fmt_lat(v) -> str:
    return f"{v:.0f}" if isinstance(v, (int, float)) else "?"


def render_tables(m: dict) -> str:
    L: list[str] = []
    L.append(f"# Eval results (judge: {m['judge_model']} vs pipeline: {m['pipeline_llm']})")
    L.append(f"pipeline_provider: {m.get('pipeline_provider', '?')} | "
             f"judge_mode: {m.get('judge', {}).get('judge_mode', '?')} | "
             f"plain_rag_llm: {m.get('plain_rag_llm_mode', '?')}")
    c = m["corpus"]
    L.append(f"Corpus: {c.get('source', '?')} — {c['num_docs']} docs / {c['num_chunks']} chunks "
             f"({c['num_real_with_source_url']} real with source_url, "
             f"{c['num_demo_without_source_url']} demo). "
             f"Gold: {m['gold']['n']} ({m['gold']['answerable']} answerable).")
    L.append("\n## Retrieval (answerable only; plain RAG uses top_k=5, rest top_k="
             f"{m.get('top_k')})")
    L.append("| system | hit_rate | recall@k | mrr |")
    L.append("|---|---|---|---|")
    for s, r in m["retrieval"].items():
        if isinstance(r, dict) and "hit_rate" in r:
            L.append(f"| {_label(s)} | {r['hit_rate']:.3f} | {r['recall@k']:.3f} | {r['mrr']:.3f} |")
    L.append("\n## Groundedness (groundedness = mean atomic-claim support, plain RAG only)")
    L.append("| system | groundedness | fabrication_count | fabrication_rate | trap_refusal_R | latency_ms |")
    L.append("|---|---|---|---|---|---|")
    for s, g in m["groundedness"].items():
        gr = f"{g.get('groundedness', float('nan')):.3f}" \
            if "groundedness" in g else f"{g['verified_rate']:.3f}*"
        L.append(f"| {_label(s)} | {gr} | {g['fabrication_count']} | "
                 f"{g['fabrication_rate']:.3f} | {g['trap_refusal_recall']:.3f} "
                 f"(n={g['n_traps']}) | {_fmt_lat(g.get('latency_ms_mean'))} |")
    L.append("*verified_rate shown for claim-pipeline systems (share of answerables "
             "with >=1 surviving claim).")
    L.append("\n## Judge (usefulness 0-5 / entailment)")
    j = m["judge"]
    L.append(f"mode: {j.get('judge_mode', '?')}")
    L.append("| system | usefulness_0_5 | entailment |")
    L.append("|---|---|---|")
    for s, v in j.items():
        if isinstance(v, dict) and "usefulness_mean" in v:
            L.append(f"| {_label(s)} | {v['usefulness_mean']:.3f} | {v['entailment_rate']:.3f} |")
    L.append("\n## Ablations")
    for name, a in m["ablations"].items():
        if isinstance(a, dict) and "retrieval" in a:
            L.append(f"- {name}: recall={a['retrieval']['recall@k']:.3f} "
                     f"fab={a['groundedness']['fabrication_rate']:.3f}")
        else:
            L.append(f"- {name}: {a}")
    L.append("\n## Hand-built queries (tunable split; holdout excluded)")
    q = m.get("queries", {})
    if "skipped" in q:
        L.append(f"queries section skipped: {q['skipped']}")
    elif "error" in q:
        L.append(f"queries section failed: {q['error']}")
    else:
        L.append(f"n={q['n']} ({q['n_answerable']} answerable), "
                 f"holdout=[{', '.join(q.get('holdout_qids', []))}]")
        L.append("| system | hit_rate | recall@k | mrr | groundedness | fab_count | trap_refusal_R | usefulness_0_5 | latency_ms |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for s in ("full_lexical_verified", "baseline_no_verify", "hybrid_verified",
                  "baseline_injected", "baseline_plain_rag"):
            r = q["retrieval"].get(s, {})
            g = q["groundedness"].get(s, {})
            ju = q["judge"].get(s, {})
            gr = (f"{g.get('groundedness', float('nan')):.3f}"
                  if "groundedness" in g
                  else f"{g.get('verified_rate', float('nan')):.3f}*")
            L.append(f"| {_label(s)} | {r.get('hit_rate', float('nan')):.3f} | "
                     f"{r.get('recall@k', float('nan')):.3f} | "
                     f"{r.get('mrr', float('nan')):.3f} | "
                     f"{gr} | {g.get('fabrication_count', '?')} | "
                     f"{g.get('trap_refusal_recall', float('nan')):.3f} | "
                     f"{ju.get('usefulness_mean', float('nan')):.3f} | "
                     f"{_fmt_lat(g.get('latency_ms_mean'))} |")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
