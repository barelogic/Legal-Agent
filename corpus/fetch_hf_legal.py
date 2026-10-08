"""Fetch HF legal datasets to data/raw/hf_legal/ as normalized JSONL rows.

Sources (public):
- sujantkumarkv/indian_legal_corpus: 1288 {text} rows (full).
- shounakpaul95/Benchmark-Testing @ refs/convert/parquet: lsi/{statutes,
  dev, test} + bail/{test_all} (caps below; train skipped by default).
- vishnun0027/Indian-Law: 25k Instruction/Response QA pairs — DERIVED, not
  primary law. Skipped by default (--with-qa to include, labelled
  [QA-DERIVED] at build time).

Row schema out: {src, file, id, text, label?, year?}. Raw parquet bytes are
NOT kept (HF hub cache is the archive); the JSONL is the inspectable raw.

Re-run: .venv/bin/python corpus/fetch_hf_legal.py [--with-train] [--with-qa]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CAPS = {  # file -> max rows (0 = skip)
    "lsi/statutes/0000.parquet": -1,  # all (100 rows)
    "lsi/dev/0000.parquet": 1000,
    "lsi/test/0000.parquet": 2000,
    "bail/test_all/0000.parquet": 500,
    "lsi/train/0000.parquet": 0,
}


def _rows_parquet(repo: str, path: str, rev: str | None,
                  limit: int) -> list[dict]:
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    local = hf_hub_download(repo, path, revision=rev, repo_type="dataset")
    t = pq.read_table(local)
    cols = t.column_names
    n = t.num_rows if limit < 0 else min(limit, t.num_rows)
    out = []
    for row in t.slice(0, n).to_pylist():
        txt = row.get("text", "")
        if isinstance(txt, dict):  # bail facts-and-arguments struct
            txt = "\n".join(
                s for v in txt.values()
                for s in (v if isinstance(v, list) else [v])
                if isinstance(s, str) and s.strip())
        elif isinstance(txt, list):
            txt = "\n".join(s for s in txt if isinstance(s, str))
        if not (isinstance(txt, str) and txt.strip()):
            continue
        out.append({"id": str(row.get("id", "")), "text": txt,
                    "label": row.get("label")})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch HF legal datasets")
    ap.add_argument("--with-train", action="store_true")
    ap.add_argument("--with-qa", action="store_true")
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    out_d = root / "data" / "raw" / "hf_legal"
    out_d.mkdir(parents=True, exist_ok=True)
    total = 0

    # 1. sujant corpus (tiny, full)
    from datasets import load_dataset

    ds = load_dataset("sujantkumarkv/indian_legal_corpus", split="train")
    rows = [{"src": "sujant", "file": "train", "id": str(i),
             "text": r["text"], "label": None}
            for i, r in enumerate(ds) if (r.get("text") or "").strip()]
    (out_d / "sujant.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    print(f"sujant: {len(rows)} rows")
    total += len(rows)

    # 2. Benchmark-Testing parquet files
    rev = "refs/convert/parquet"
    caps = dict(CAPS)
    if args.with_train:
        caps["lsi/train/0000.parquet"] = 5000
    for path, lim in caps.items():
        if lim == 0:
            continue
        rows = _rows_parquet("shounakpaul95/Benchmark-Testing", path, rev, lim)
        slug = path.replace("/", "_").replace(".parquet", "")
        for r in rows:
            r.update(src="benchmark-testing", file=slug)
        (out_d / f"{slug}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        print(f"{slug}: {len(rows)} rows")
        total += len(rows)

    # 3. Indian-Law QA (derived; opt-in)
    if args.with_qa:
        ds = load_dataset("vishnun0027/Indian-Law", split="train")
        rows = [{"src": "indian-law-qa", "file": "train",
                 "id": str(i),
                 "text": f"Q: {r.get('Instruction', '')}\nA: {r.get('Response', '')}",
                 "label": None}
                for i, r in enumerate(ds)
                if (r.get("Response") or "").strip()]
        (out_d / "indian_law_qa.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        print(f"indian-law-qa: {len(rows)} rows")
        total += len(rows)
    else:
        print("indian-law-qa: skipped (derived Q&A, use --with-qa)")

    (root / "data" / "raw" / "_hf_legal_manifest.json").write_text(
        json.dumps({"total_rows": total, "with_train": args.with_train,
                    "with_qa": args.with_qa}, indent=1), encoding="utf-8")
    print(f"total: {total} rows -> {out_d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
