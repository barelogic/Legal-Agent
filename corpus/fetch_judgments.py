"""Fetch 15-25 bail judgments from HF indian-case-laws (public, apache-2.0).

Keeps rows whose disposition mentions bail (matched case-insensitively on
fetched values, never a hardcoded list), with non-empty text, spread
across courts. Raw rows -> data/raw/hf_bail/<doc_id>.json + manifest.
Ingest into Docs happens in corpus/build_corpus.py via P1 row_to_doc.

Re-run: .venv/bin/python corpus/fetch_judgments.py [--target 20]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _has_text(row: dict) -> bool:
    return bool((row.get("indexable_text") or "").strip()
                or (row.get("headnote_text") or "").strip())


def fetch_bail_rows(target: int = 20, max_scan: int = 60000) -> list[dict]:
    """Stream HF rows; keep bail-disposition rows with text, diverse courts."""
    from ingest.hf_cases import iter_hf_rows

    kept: list[dict] = []
    seen_courts: Counter = Counter()
    seen_disps: Counter = Counter()
    for row in iter_hf_rows(limit=max_scan * 2, max_scan=max_scan):
        disp = (row.get("disposition_text") or "").upper()
        if "BAIL" not in disp:
            continue
        if not _has_text(row):
            continue
        court = row.get("court_name") or "unknown"
        # cap per-court to force diversity; always take Supreme Court rows
        if seen_courts[court] >= 4 and "SUPREME" not in court.upper():
            continue
        kept.append(row)
        seen_courts[court] += 1
        seen_disps[disp] += 1
        if len(kept) >= target:
            break
    print(f"courts: {dict(seen_courts)}")
    print(f"dispositions: {dict(seen_disps)}")
    return kept


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch bail judgments from HF")
    ap.add_argument("--target", type=int, default=20)
    ap.add_argument("--max-scan", type=int, default=60000)
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    out = root / "data" / "raw" / "hf_bail"
    out.mkdir(parents=True, exist_ok=True)
    rows = fetch_bail_rows(target=args.target, max_scan=args.max_scan)
    manifest: list[dict] = []
    for row in rows:
        cnr = (row.get("cnr_number") or row.get("case_metadata_id") or "norow").strip()
        safe = "".join(c if c.isalnum() else "_" for c in cnr)[:60]
        p = out / f"{safe}.json"
        p.write_text(json.dumps(row, indent=1, default=str), encoding="utf-8")
        manifest.append({
            "path": str(p),
            "case_title": row.get("case_title"),
            "court": row.get("court_name"),
            "decision_date": row.get("decision_date"),
            "disposition": row.get("disposition_text"),
            "source_url": row.get("source_pdf_s3_url"),
            "accessed": date.today().isoformat(),
        })
    (root / "data" / "raw" / "_hf_bail_manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"saved {len(rows)} rows to {out}")
    if len(rows) < 15:
        print("WARNING: fewer than 15 bail rows found; widen max-scan")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
