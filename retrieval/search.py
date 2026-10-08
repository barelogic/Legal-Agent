"""CLI: python -m retrieval.search "query" [--top-k 8] [--doc-ids a,b]."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrieval.hybrid import retrieve  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Parse args, run retrieve, print chunk_id, score and text preview."""
    ap = argparse.ArgumentParser(description="Hybrid search over ingested chunks")
    ap.add_argument("query", help="search query")
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--doc-ids", default="", help="comma-separated doc_id filter")
    ap.add_argument("--min-overlap", type=int, default=2, help="lexical gate lever")
    args = ap.parse_args(argv)
    doc_ids = [d.strip() for d in args.doc_ids.split(",") if d.strip()] or None
    hits = retrieve(args.query, top_k=args.top_k, doc_ids=doc_ids, min_overlap=args.min_overlap)
    for chunk, score in hits:
        preview = " ".join(chunk.text.split())[: 160]
        print(f"{chunk.chunk_id}\t{score:.4f}\t{preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
