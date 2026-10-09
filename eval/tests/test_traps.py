"""Trap-expansion integrity (pure JSON, no corpus/LLM)."""

import json
from pathlib import Path


def _rows():
    p = Path(__file__).resolve().parent.parent / "queries.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def test_counts():
    rows = _rows()
    assert len(rows) == 50
    assert sum(1 for r in rows if r.get("trap")) == 20
    assert sum(1 for r in rows if r.get("holdout")) == 14
    assert sum(1 for r in rows if r.get("answerable")) == 30


def test_new_traps_shape():
    rows = {r["qid"]: r for r in _rows()}
    for i in range(41, 51):
        r = rows[f"q{i:03d}"]
        assert r["trap"] is True and r["answerable"] is False
        assert r["answer_span"] == ""
    assert [rows[f"q{i:03d}"]["holdout"] for i in range(41, 51)] == [
        False, True, False, True, False, False, True, False, False, True]
    # categories present: fake cases, absent sections, absent facts, wrong year/court
    qs = " ".join(rows[f"q{i:03d}"]["question"] for i in range(41, 51))
    for needle in ["Pawan Kumar Gupta", "BNS s.500", "BNSS s.600", "BSA s.300",
                   "banks", "surety", "2024INSC735", "Bombay", "Subramani",
                   "Chandan Kumar"]:
        assert needle in qs, needle
