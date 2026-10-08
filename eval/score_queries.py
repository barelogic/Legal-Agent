"""Score systems on eval/queries.jsonl (non-holdout only).

Holdout items (holdout=true) are never scored here; they ship for the
judges. Reuses eval systems + metric modules so numbers match run_all.
Used by eval/run_all.py; runnable standalone prints a compact table.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.judge import judge_answers
from eval.metrics_grounded import groundedness_report
from eval.metrics_retrieval import retrieval_report
from eval.systems import run_system

SYSTEMS = ("full_lexical_verified", "baseline_no_verify", "hybrid_verified",
           "baseline_injected")


def load_processed_corpus() -> tuple[dict, dict]:
    """Docs/chunks of the built eval corpus (data/processed/, P1 ingest output)."""
    from ingest.pipeline import load_chunks, load_docs

    docs = {d.doc_id: d for d in load_docs()}
    chunks = {c.chunk_id: c for c in load_chunks()}
    assert docs and chunks, "empty data/processed/; run corpus/build_corpus.py first"
    return docs, chunks


def load_resolved(holdout: bool = False) -> list[dict]:
    """Load resolved queries; holdout=False scores the tunable split only."""
    p = Path(__file__).resolve().parent / "datasets" / "queries_resolved.jsonl"
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [r for r in rows if bool(r.get("holdout")) == holdout]


def score_queries(docs: dict, chunks: dict, top_k: int = 4) -> dict:
    """Run all systems on non-holdout queries. Returns metric dicts."""
    rows = load_resolved(holdout=False)
    assert rows, "empty tunable split; run eval/build_queries.py first"
    answers = {s: [run_system(s, r["question"], docs, chunks, top_k=top_k)
                   for r in rows] for s in SYSTEMS}
    return {
        "n": len(rows),
        "n_answerable": sum(1 for r in rows if r.get("answerable")),
        "retrieval": retrieval_report(rows, docs, chunks, systems=SYSTEMS, top_k=top_k),
        "groundedness": groundedness_report(answers, rows, docs, chunks),
        "judge": judge_answers(answers, rows),
    }


def main(argv: list[str] | None = None) -> int:
    docs, chunks = load_processed_corpus()
    out = score_queries(docs, chunks)
    print(json.dumps(
        {s: {"retrieval": out["retrieval"][s], "groundedness": out["groundedness"][s]}
         for s in SYSTEMS}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
