"""Per-trap max token overlap vs the corpus (near-vocab trap design log).

For every trap row in eval/queries.jsonl: max over chunks of
|Qtok ∩ Ctok| / |Qtok| (coverage) and raw overlap count, using the same
content-token rule as retrieval/store.py. A trap BELOW the min_overlap gate
refuses trivially (weak trap); a trap near/above MIN_COVERAGE stresses the
relevance gates + verifier (strong trap). Re-run after any corpus rebuild:
overlap is vocab-dependent.

Re-run: .venv/bin/python eval/trap_overlap.py [--out eval/results/trap_overlap.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="trap max-overlap log")
    ap.add_argument("--out", default="eval/results/trap_overlap.json")
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parent.parent

    from ingest.pipeline import load_chunks
    from retrieval.store import _content_tokens

    rows = [json.loads(x) for x in (root / "eval" / "queries.jsonl")
            .read_text(encoding="utf-8").splitlines() if x.strip()]
    traps = [r for r in rows if r.get("trap") is True]
    chunks = load_chunks()
    csets = [(c.chunk_id, c.doc_id, set(_content_tokens(c.text))) for c in chunks]
    print(f"{len(traps)} traps vs {len(csets)} chunks")
    log = []
    for r in traps:
        qtok = set(_content_tokens(r["question"]))
        best = (0, 0.0, None, None)
        for cid, doc, cs in csets:
            ov = len(qtok & cs)
            cov = ov / max(1, len(qtok))
            if (ov, cov) > (best[0], best[1]):
                best = (ov, cov, cid, doc)
        ov, cov, cid, doc = best
        log.append({"qid": r["qid"], "question": r["question"],
                    "holdout": bool(r.get("holdout")),
                    "n_qtok": len(qtok), "max_overlap": ov,
                    "max_coverage": round(cov, 3), "argmax_chunk": cid,
                    "argmax_doc": doc})
        print(f"{r['qid']} holdout={int(bool(r.get('holdout')))} "
              f"qtok={len(qtok):3d} max_ov={ov:3d} cov={cov:.3f} <- {doc}")
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(log, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
