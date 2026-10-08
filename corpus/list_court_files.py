"""List Indian court judgment archives (S3, public, read-only discovery).

Probes both buckets via the S3 ListBucket XML API (no credentials, no
downloads) and prints years / courts / benches with tar sizes, so fetch
commands can be scoped BEFORE pulling gigabytes. This is the `--discover`
step: exact file names come from the buckets themselves, never memory.

Re-run:
    .venv/bin/python corpus/list_court_files.py [--years 2020,2024]
    .venv/bin/python corpus/list_court_files.py --source hc --year 2020
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SC_BASE = "https://indian-supreme-court-judgments.s3.amazonaws.com"
HC_BASE = "https://indian-high-court-judgments.s3.amazonaws.com"


def _get(url: str, timeout: int = 30) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def list_prefixes(base: str, prefix: str) -> list[str]:
    """Child prefixes under prefix (S3 delimiter trick)."""
    out: list[str] = []
    token = ""
    while True:
        url = f"{base}/?list-type=2&delimiter=%2F&prefix={prefix}"
        if token:
            url += f"&continuation-token={token}"
        root = ET.fromstring(_get(url))
        ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
        for cp in root.iter(ns + "CommonPrefixes"):
            p = cp.find(ns + "Prefix")
            if p is not None and p.text:
                out.append(p.text)
        t = root.find(ns + "NextContinuationToken")
        token = t.text.strip() if t is not None and t.text else ""
        if not token:
            return out


def list_keys(base: str, prefix: str, limit: int = 20) -> list[tuple[str, int]]:
    """(key, size) pairs under prefix."""
    url = f"{base}/?list-type=2&max-keys={limit}&prefix={prefix}"
    root = ET.fromstring(_get(url))
    ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
    out = []
    for c in root.iter(ns + "Contents"):
        k = c.find(ns + "Key").text  # type: ignore[union-attr]
        s = int(c.find(ns + "Size").text or 0)  # type: ignore[union-attr]
        out.append((k, s))
    return out


def sc_years() -> list[str]:
    return sorted(
        m.group(1)
        for p in list_prefixes(SC_BASE, "data%2Ftar%2F")
        if (m := re.match(r"data/tar/year=(\d{4})/", p))
    )


def hc_courts(year: str) -> list[str]:
    return sorted(
        m.group(1)
        for p in list_prefixes(HC_BASE, f"data%2Ftar%2Fyear%3D{year}%2F")
        if (m := re.match(rf"data/tar/year={year}/(court=[^/]+)/", p))
    )


def hc_benches(year: str, court: str) -> list[tuple[str, int]]:
    """[(bench, tar_bytes)] for one court-year (index.json sizes skipped)."""
    out = []
    for p in list_prefixes(HC_BASE, f"data%2Ftar%2Fyear%3D{year}%2F{court}%2F"):
        m = re.match(rf"data/tar/year={year}/{court}/(bench=[^/]+)/", p)
        if not m:
            continue
        size = sum(s for k, s in list_keys(HC_BASE, p.replace("/", "%2F"), 50)
                   if k.endswith(".tar"))
        out.append((m.group(1), size))
    return sorted(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Discover court archive layout")
    ap.add_argument("--source", default="both", choices=("sc", "hc", "both"))
    ap.add_argument("--year", default="")
    ap.add_argument("--years", default="")
    args = ap.parse_args(argv)

    if args.source in ("sc", "both"):
        years = args.years.split(",") if args.years else sc_years()
        print("== supreme court: data/tar/year=YYYY/english/{english.tar + .index.json} + metadata ==")
        for y in years:
            keys = list_keys(SC_BASE, f"data%2Ftar%2Fyear%3D{y}%2Fenglish%2F", 5)
            tar = next((s for k, s in keys if k.endswith(".tar")), 0)
            n = len([k for k, _ in keys])
            print(f"  year={y} tar={tar / 1e6:.0f}MB keys~{n}")
    if args.source in ("hc", "both"):
        years = [args.year] if args.year else (
            args.years.split(",") if args.years else ["2020"])
        print("== high courts: data/tar/year=YYYY/court=N_M/bench=NAME/data.tar ==")
        for y in years:
            for court in hc_courts(y):
                benches = hc_benches(y, court)
                tot = sum(s for _, s in benches)
                print(f"  year={y} {court}: {len(benches)} benches, {tot / 1e6:.0f}MB")
                for b, s in benches:
                    print(f"    {b}: {s / 1e6:.0f}MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
