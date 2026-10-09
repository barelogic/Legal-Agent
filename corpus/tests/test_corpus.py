"""Corpus self-tests: pure helpers + committed artifact schemas (offline)."""

import json
from pathlib import Path

from corpus.build_section_map import REPEAL_PATTERNS
from corpus.fetch_statutes import _slug, strip_html

ROOT = Path(__file__).resolve().parent.parent.parent


def test_slug_and_strip():
    assert _slug("BNSS 2023 (final).pdf".rsplit(".", 1)[0]) == "bnss_2023_final"
    assert strip_html("<span>a</span> &amp;  b") == "a & b"


def test_section_map_rows_all_sourced():
    m = json.loads((ROOT / "corpus" / "section_map.json").read_text(encoding="utf-8"))
    assert m["rows"], "map must never be empty-memory; fail instead"
    for r in m["rows"]:
        assert r["source_url"].startswith("https://"), r
        assert r["origin"] in ("repeal-section", "official-comparison-chart"), r
        assert r["quote"] and len(r["quote"]) > 20, r


def test_repeal_patterns_cover_three_acts():
    keys = {p[0] for p in REPEAL_PATTERNS}
    assert len(keys) == 3 and all("2023" in k for k in keys)


def test_manifest_every_doc_has_provenance():
    m = json.loads((ROOT / "corpus" / "manifest.json").read_text(encoding="utf-8"))
    assert len(m) >= 40, f"expected >=40 docs, got {len(m)}"
    for d in m:
        assert d["doc_id"] and d["title"] and d["doc_type"] in (
            "statute", "judgment", "case_file"), d
        assert d["source_url"] or d["synthetic"], d  # every doc: URL or labelled synthetic
        assert d["num_chunks"] >= 1, d


def test_queries_format():
    rows = [json.loads(x) for x in
            (ROOT / "eval" / "queries.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 50
    by_wf: dict[str, int] = {}
    for r in rows:
        by_wf[r["workflow"]] = by_wf.get(r["workflow"], 0) + 1
        assert set(r) >= {"qid", "workflow", "question", "answer_span",
                          "answerable", "trap", "holdout"}
        assert (r["answer_span"] == "") == (not r["answerable"])
    assert by_wf == {"chat": 13, "review": 12, "research": 13, "draft": 12}
    assert sum(1 for r in rows if r["trap"]) == 20
    assert sum(1 for r in rows if r["holdout"]) == 14
