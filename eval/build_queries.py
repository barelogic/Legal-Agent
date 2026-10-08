"""Resolve eval/queries.jsonl against P1 ingest output (data/processed/).

For each answerable item: the answer_span must be a verbatim substring of
>=1 chunk; gold_chunk_ids/gold_doc_ids are filled from the match. Any
miss FAILS loudly (exit 2) instead of drifting. Trap items must carry an
empty span. Writes eval/datasets/queries_resolved.jsonl (generated).

Re-run: .venv/bin/python eval/build_queries.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def load_queries(path: Path) -> list[dict]:
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 40, f"expected 40 queries, got {len(rows)}"
    return rows


def main(argv: list[str] | None = None) -> int:
    from ingest.pipeline import load_chunks

    root = Path(__file__).resolve().parent.parent
    rows = load_queries(root / "eval" / "queries.jsonl")
    chunks = load_chunks()
    assert chunks, "no chunks in data/processed/; run corpus/build_corpus.py first"
    by_wf: dict[str, int] = {}
    n_trap = n_hold = 0
    resolved: list[dict] = []
    errors: list[str] = []
    for r in rows:
        by_wf[r["workflow"]] = by_wf.get(r["workflow"], 0) + 1
        n_trap += bool(r.get("trap"))
        n_hold += bool(r.get("holdout"))
        span = r.get("answer_span", "")
        if r.get("answerable"):
            if not span:
                errors.append(f"{r['qid']}: answerable but empty span")
                continue
            hits = [c for c in chunks if span in c.text]
            if not hits:
                errors.append(f"{r['qid']}: span not found verbatim in any chunk")
                continue
            r = dict(r, gold_chunk_ids=sorted(c.chunk_id for c in hits),
                     gold_doc_ids=sorted({c.doc_id for c in hits}))
        else:
            if span:
                errors.append(f"{r['qid']}: trap/unanswerable must have empty span")
                continue
            r = dict(r, gold_chunk_ids=[], gold_doc_ids=[])
        resolved.append(r)
    assert by_wf == {"chat": 10, "review": 10, "research": 10, "draft": 10}, by_wf
    assert n_trap == 10, f"need 10 traps, got {n_trap}"
    assert n_hold == 10, f"need 10 holdout, got {n_hold}"
    if errors:
        print("QUERY ERRORS:"); [print(" -", e) for e in errors]
        return 2
    out = root / "eval" / "datasets" / "queries_resolved.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r) for r in resolved) + "\n", encoding="utf-8")
    print(f"resolved {len(resolved)} queries "
          f"({sum(1 for r in resolved if r['answerable'])} answerable) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
