"""Download court judgment tars (S3, public) + per-file metadata.

Generic over both buckets: given an index.json URL + its tar URL, saves
  data/raw/<area>/<path...>/data.tar + files.json (the index listing)
  data/raw/<area>/<path...>/meta.json (optional metadata index listing)
Tars are NOT unpacked here (build_corpus.py streams members). A fetch
manifest records byte counts so re-runs skip completed downloads.

Re-run:
    .venv/bin/python corpus/fetch_court_tars.py --sc-years 2024
    .venv/bin/python corpus/fetch_court_tars.py --hc-bench 2020 court=19_16 bench=calcutta_original_side
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SC_BASE = "https://indian-supreme-court-judgments.s3.amazonaws.com"
HC_BASE = "https://indian-high-court-judgments.s3.amazonaws.com"


def _dl(url: str, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        print(f"  have {dest.name} ({dest.stat().st_size / 1e6:.1f}MB), skip")
        return dest.stat().st_size
    req = urllib.request.Request(url, headers={"User-Agent": "legal-agent-corpus/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        n = 0
        while True:
            blk = r.read(1 << 20)
            if not blk:
                break
            f.write(blk)
            n += len(blk)
    print(f"  got {dest.name} ({n / 1e6:.1f}MB)")
    return n


def fetch_sc_year(root: Path, year: str) -> dict:
    d = root / "data" / "raw" / "sc" / f"year={year}"
    idx_url = f"{SC_BASE}/data/tar/year={year}/english/english.index.json"
    tar_url = f"{SC_BASE}/data/tar/year={year}/english/english.tar"
    mdx_url = f"{SC_BASE}/metadata/tar/year={year}/metadata.index.json"
    mdt_url = f"{SC_BASE}/metadata/tar/year={year}/metadata.tar"
    _dl(idx_url, d / "english.index.json")
    idx = json.loads((d / "english.index.json").read_text(encoding="utf-8"))
    _dl(tar_url, d / "english.tar")
    try:
        _dl(mdx_url, d / "metadata.index.json")
        _dl(mdt_url, d / "metadata.tar")
        meta = True
    except Exception as e:
        print(f"  metadata skipped ({e})")
        meta = False
    return {"area": "sc", "year": year, "index_url": idx_url, "tar_url": tar_url,
            "files": idx.get("file_count"), "meta": meta}


def fetch_hc_bench(root: Path, year: str, court: str, bench: str) -> dict:
    sub = f"year={year}/{court}/{bench}"
    d = root / "data" / "raw" / "hc" / sub
    idx_url = f"{HC_BASE}/data/tar/{sub}/data.index.json"
    tar_url = f"{HC_BASE}/data/tar/{sub}/data.tar"
    _dl(idx_url, d / "data.index.json")
    idx = json.loads((d / "data.index.json").read_text(encoding="utf-8"))
    _dl(tar_url, d / "data.tar")
    return {"area": "hc", "year": year, "court": court, "bench": bench,
            "index_url": idx_url, "tar_url": tar_url,
            "files": idx.get("file_count")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch court tars")
    ap.add_argument("--sc-years", default="")
    ap.add_argument("--hc-bench", nargs=3, action="append", default=[],
                    metavar=("YEAR", "COURT", "BENCH"))
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    log_p = root / "data" / "raw" / "_court_fetch_log.json"
    log = json.loads(log_p.read_text()) if log_p.is_file() else []
    for y in [x for x in args.sc_years.split(",") if x]:
        print(f"SC year={y}")
        log.append(fetch_sc_year(root, y))
    for y, court, bench in args.hc_bench:
        print(f"HC {y} {court} {bench}")
        log.append(fetch_hc_bench(root, y, court, bench))
    if log:
        log_p.write_text(json.dumps(log, indent=1), encoding="utf-8")
    if not log:
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
