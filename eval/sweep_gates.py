"""Threshold sweep: MIN_COVERAGE x RERANK on dev only (never holdout).

Retrieval-level (no LLM): per config, answerable recall@k (gold chunks)
vs trap empty-retrieval rate. Knee = highest trap-empty rate with recall
within 0.02 of max. Reports; changes nothing (P1 owns the defaults).

Re-run: .venv/bin/python eval/sweep_gates.py [--top-k 4]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

COVERAGES = [0.0, 0.2, 0.32, 0.4, 0.5]
RERANKS = ["bypass", "cutoff"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="gate threshold sweep (dev only)")
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--out", default="eval/results/sweep.json")
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parent.parent

    from eval.score_queries import load_resolved, try_load_processed_corpus

    docs, chunks = try_load_processed_corpus()
    if not docs:
        print("no data/processed/; run corpus/build_corpus.py first")
        return 2
    rows = load_resolved(holdout=False)

    from retrieval.hybrid import HybridIndex

    print("building index ...", flush=True)
    hidx = HybridIndex(list(chunks.values()))
    ans_rows = [r for r in rows if r.get("answerable")]
    trap_rows = [r for r in rows if r.get("trap")]
    print(f"dev: {len(rows)} rows ({len(ans_rows)} answerable, "
          f"{len(trap_rows)} traps); holdout excluded", flush=True)
    out = []
    for cov in COVERAGES:
        for rr in RERANKS:
            if rr == "bypass":
                os.environ["VERIFY_RERANK"] = "0"
                rmin = float("-inf")
            else:
                os.environ.pop("VERIFY_RERANK", None)
                rmin = None  # env RERANK_MIN_SCORE
            t0 = time.time()
            rec = empty = 0
            for r in ans_rows:
                ranked = [c.chunk_id for c, _ in
                          hidx.retrieve(r["question"], top_k=args.top_k,
                                        min_coverage=cov, rerank_min_score=rmin)]
                gold = set(r.get("gold_chunk_ids", []))
                rec += len(gold & set(ranked)) / max(1, len(gold))
            for r in trap_rows:
                ranked = hidx.retrieve(r["question"], top_k=args.top_k,
                                       min_coverage=cov, rerank_min_score=rmin)
                empty += (len(ranked) == 0)
            row = {"min_coverage": cov, "rerank": rr,
                   "recall@k": round(rec / max(1, len(ans_rows)), 3),
                   "trap_empty_rate": round(empty / max(1, len(trap_rows)), 3),
                   "n_ans": len(ans_rows), "n_trap": len(trap_rows),
                   "seconds": round(time.time() - t0, 1)}
            out.append(row)
            print(row, flush=True)
    best_rec = max(r["recall@k"] for r in out)
    cand = [r for r in out if r["recall@k"] >= best_rec - 0.02]
    knee = max(cand, key=lambda r: (r["trap_empty_rate"], r["min_coverage"]))
    res = {"top_k": args.top_k, "grid": out, "knee": knee,
           "rule": "highest trap_empty_rate with recall within 0.02 of max"}
    p = root / args.out
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("KNEE:", json.dumps(knee))
    print(f"wrote {p} (defaults unchanged — recommendation only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
