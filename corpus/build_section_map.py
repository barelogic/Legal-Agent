"""Build corpus/section_map.json from OFFICIAL sources only.

Row sources (all fetched, nothing from memory):
1. Repeal cross-references extracted verbatim from the three MHA bare-Act
   PDFs (BNSS s.531, BNS s.358, BSA s.170): which old Act each new Act
   repeals, with quote + MHA source_url + chunk_id.
2. Optional: an official comparative chart CSV
   (--chart path, columns: old_act,old_section,new_act,new_section).
   Every chart row must carry --chart-url (official URL the file came
   from); without it the chart is rejected. Absent a fetchable official
   chart, the map ships with repeal rows only and coverage documents
   the gap + attempted sources (corpus/sources.py COMPARISON_SOURCES_ATTEMPTED).

Re-run: .venv/bin/python corpus/build_section_map.py [--chart FILE --chart-url URL]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from corpus.sources import COMPARISON_SOURCES_ATTEMPTED

# (pdf_key, regex with groups: new_section, old_act) — patterns matched
# against extracted PDF page text, never hand-filled.
REPEAL_PATTERNS = [
    ("the_bharatiya_nagarik_suraksha_sanhita_2023",
     r"(\d{1,3})\.\s*\(1\)\s*The (Code of Criminal Procedure, 1973) is hereby\s*repealed",
     "BNSS", "https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf"),
    ("the_bharatiya_nyaya_sanhita_2023",
     r"(\d{1,3})\.\s*\(1\)\s*The (Indian Penal Code) is hereby\s*repealed",
     "BNS", "https://www.mha.gov.in/sites/default/files/2024-04/250883_english_01042024.pdf"),
    ("the_bharatiya_sakshya_adhiniyam_2023",
     r"(\d{1,3})\.\s*\(1\)\s*The (Indian Evidence Act, 1872) is hereby\s*repealed",
     "BSA", "https://www.mha.gov.in/sites/default/files/2024-04/250882_english_01042024_0.pdf"),
]


def extract_repeal_rows(raw: Path) -> list[dict]:
    """Extract repeal cross-references from MHA PDF page text."""
    from ingest.pdf import extract_pages

    rows: list[dict] = []
    for pdf_key, pattern, _new_short, url in REPEAL_PATTERNS:
        pdf = raw / "statutes" / f"{pdf_key}.pdf"
        if not pdf.is_file():
            print(f"skip repeal ({pdf.name} missing; run fetch_statutes.py)")
            continue
        for page_no, text in extract_pages(pdf):
            m = re.search(pattern, text)
            if not m:
                continue
            raw_quote = " ".join(m.group(0).split())
            # PDF text extraction drops the space at some line breaks
            # ("herebyrepealed"). The regex above only matches when the
            # source reads "hereby <space> repealed" modulo extraction
            # spacing, so restoring the space reproduces the official
            # wording; the fix is flagged, never silent.
            quote, n_fix = re.subn(r"herebyrepealed", "hereby repealed", raw_quote)
            rows.append({
                "old_act": m.group(2),
                "old_section": None,
                "new_act": pdf_key.replace("the_", "").replace("_2023", ""),
                "new_section": m.group(1),
                "relation": "repealed-by",
                "quote": quote,
                "quote_normalized": bool(n_fix),
                "source_url": url,
                "origin": "repeal-section",
            })
            break
    # de-dupe by (old_act, new_section)
    seen: set[tuple] = set()
    uniq = [r for r in rows if not ((r["old_act"], r["new_section"]) in seen
                                    or seen.add((r["old_act"], r["new_section"])))]
    return uniq


def load_chart(chart: Path, chart_url: str) -> list[dict]:
    """Ingest an official comparative-chart CSV. URL required per row."""
    if not chart_url.startswith("https://"):
        raise ValueError("chart-url must be an official https URL (got %r)" % chart_url)
    rows: list[dict] = []
    with chart.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            for col in ("old_act", "old_section", "new_act", "new_section"):
                if not (rec.get(col) or "").strip():
                    raise ValueError(f"chart row missing {col}: {rec}")
            rows.append({
                "old_act": rec["old_act"].strip(),
                "old_section": rec["old_section"].strip() or None,
                "new_act": rec["new_act"].strip(),
                "new_section": rec["new_section"].strip() or None,
                "relation": (rec.get("relation") or "corresponds-to").strip(),
                "quote": (rec.get("quote") or "").strip(),
                "source_url": chart_url,
                "origin": "official-comparison-chart",
            })
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build section_map.json (official sources only)")
    ap.add_argument("--chart", default=None, help="official comparative-chart CSV")
    ap.add_argument("--chart-url", default="", help="official URL the chart came from")
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    rows = extract_repeal_rows(root / "data" / "raw")
    origin = "repeal-cross-references-only"
    if args.chart:
        if not args.chart_url:
            print("refusing chart without --chart-url (every row must carry source_url)")
            return 2
        rows.extend(load_chart(Path(args.chart), args.chart_url))
        origin = "repeal-cross-references+official-chart"
    if not rows:
        print("no rows extracted; cannot build map from memory; aborting")
        return 2
    if any(not r["source_url"] for r in rows):
        print("refusing rows without source_url")
        return 2
    (root / "corpus" / "section_map.json").write_text(json.dumps({
        "coverage": origin,
        "note": "Full old-new section correspondence requires the official "
                "comparison charts (BPR&D/MHA), unreachable from this environment; "
                "see attempted sources. Repeal rows are verbatim from MHA PDFs.",
        "attempted_official_chart_sources": COMPARISON_SOURCES_ATTEMPTED,
        "rows": rows,
    }, indent=1), encoding="utf-8")
    print(f"section_map: {len(rows)} rows ({origin})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
