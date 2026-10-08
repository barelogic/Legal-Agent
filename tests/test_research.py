"""Research workflow: verified law + section-map lookup, never a guess."""

import json

from contracts.schemas import Chunk, Doc
from generation.llm import MockClient
from retrieval.store import Registry
from workflows.research import (
    extract_old_law_mentions,
    lookup_mapping,
    run_research,
)

QUESTION = "What is the scope of IPC Section 420 cheating?"
CASE_TEXT = "The complaint cites IPC Section 420 for cheating."
LAW_TEXT = "Cheating under IPC Section 420 is punishable."

REPEAL_ONLY_MAP = {"coverage": "repeal-cross-references-only", "rows": [
    {"old_act": "Indian Penal Code", "old_section": None, "new_act": "bharatiya_nyaya_sanhita",
     "new_section": "358", "relation": "repealed-by", "quote": "The Indian Penal Code is hereby repealed",
     "source_url": "https://example.com/bns.pdf"},
]}

GOOD_MAP = {"rows": [
    {"old_act": "Indian Penal Code", "old_section": "420", "new_act": "bharatiya_nyaya_sanhita",
     "new_section": "316", "relation": "corresponds-to", "quote": "Section 316 punishes cheating",
     "source_url": "https://example.com/chart.pdf"},
    {"old_act": "Indian Penal Code", "old_section": "421", "new_act": "bharatiya_nyaya_sanhita",
     "new_section": "317", "relation": "corresponds-to", "quote": "x", "source_url": ""},
]}


def _reg() -> Registry:
    reg = Registry()
    reg.register_doc(Doc(doc_id="case1", title="Case file", doc_type="case_file"))
    reg.register_doc(Doc(doc_id="bns_2023", title="Bharatiya Nyaya Sanhita", doc_type="statute"))
    reg.chunks["case1::p1::c0"] = Chunk(chunk_id="case1::p1::c0", doc_id="case1", text=CASE_TEXT)
    reg.chunks["bns_2023::p1::c0"] = Chunk(
        chunk_id="bns_2023::p1::c0", doc_id="bns_2023", text=LAW_TEXT)
    return reg


def _map(tmp_path, monkeypatch, payload, name="secmap.json"):
    p = tmp_path / name
    p.write_text(json.dumps(payload))
    monkeypatch.setenv("SECTION_MAP_PATH", str(p))
    return p


def test_no_verified_row_gives_missing_not_guess(tmp_path, monkeypatch):
    _map(tmp_path, monkeypatch, REPEAL_ONLY_MAP)  # same shape as the real file
    ans = run_research(question=QUESTION, doc_ids=["case1"], registry=_reg(), llm=MockClient())
    assert not ans.refused
    assert len(ans.missing_info) == 1
    assert ans.missing_info[0].why_needed == "no verified old-to-new mapping available"
    assert "indian penal code Section 420" in ans.missing_info[0].field
    # No guessed new-law section in the text.
    assert "316" not in ans.text and "BNS" not in ans.text
    assert "[MISSING:" in ans.text
    assert all(c.resolved for c in ans.citations)


def test_verified_row_shown_with_source_url(tmp_path, monkeypatch):
    _map(tmp_path, monkeypatch, GOOD_MAP)
    ans = run_research(question=QUESTION, doc_ids=["case1"], registry=_reg(), llm=MockClient())
    assert not ans.refused
    assert "Section 420 → bharatiya_nyaya_sanhita Section 316" in ans.text
    assert "https://example.com/chart.pdf" in ans.text
    assert ans.missing_info == []


def test_row_without_source_url_is_unverified(tmp_path, monkeypatch):
    _map(tmp_path, monkeypatch, GOOD_MAP)
    ans = run_research(question="Scope of IPC Section 421?", doc_ids=["case1"],
                       registry=_reg(), llm=MockClient())
    assert any("421" in m.field for m in ans.missing_info)


def test_mentions_and_lookup_units():
    assert ("indian penal code", "420") in extract_old_law_mentions(QUESTION)
    assert extract_old_law_mentions("Section 420 applies.") == []  # no Act: no guess
    assert lookup_mapping(GOOD_MAP["rows"], "indian penal code", "420")["new_section"] == "316"
    assert lookup_mapping(GOOD_MAP["rows"], "indian penal code", "999") is None
    assert lookup_mapping(REPEAL_ONLY_MAP["rows"], "indian penal code", "420") is None
