"""Render-helper tests: grounding rule is enforced before any Streamlit code."""

import pytest

from contracts.schemas import Citation, Claim, Doc
from ui.render import (
    citation_to_markdown,
    claim_markers,
    claim_to_markdown,
    docs_by_id,
    dropped_claims,
    highlight_quote,
    split_text_markers,
    status_badge,
    validate_claim_renderable,
    verified_claims,
)
from contracts.schemas import Answer


def _doc() -> Doc:
    return Doc(doc_id="bnss_2023", title="BNSS excerpt", doc_type="statute", citation="BNSS, 2023")


def _claim(**kw) -> Claim:
    base = {"claim_id": "c1", "text": "Bail is discretionary.", "chunk_ids": ["bnss_2023::p1::c1"], "quote": "judicial discretion"}
    base.update(kw)
    return Claim(**base)


def test_validate_rejects_missing_source():
    with pytest.raises(ValueError):
        validate_claim_renderable(_claim(chunk_ids=[]))
    with pytest.raises(ValueError):
        validate_claim_renderable(_claim(quote="   "))


def test_claim_markdown_links_source():
    md = claim_to_markdown(_claim(), docs_by_id([_doc()]))
    assert "Bail is discretionary." in md
    assert "judicial discretion" in md
    assert "bnss_2023::p1::c1" in md
    assert "BNSS excerpt" in md


def test_citation_unresolved_flagged():
    md = citation_to_markdown(Citation(cite_id="k1", raw="[1]", resolved=False), {})
    assert "unresolved" in md


def test_verified_vs_dropped_split():
    ans = Answer(
        workflow="chat",
        text="x",
        claims=[_claim(status="verified"), _claim(claim_id="c2", status="unsupported")],
        citations=[],
    )
    assert [c.claim_id for c in verified_claims(ans)] == ["c1"]
    assert [c.claim_id for c in dropped_claims(ans)] == ["c2"]


def test_split_text_markers_chips():
    parts = split_text_markers("Bail is discretionary [c1] and noted [c2].")
    assert ("[c1]", "c1") in [(p[0], p[1]) for p in parts]
    assert claim_markers("a [c1] b [c2] c [c1]") == ["c1", "c2"]


def test_highlight_quote_marks_span():
    out = highlight_quote("the court held bail is the rule here", "bail is the rule")
    assert "<mark>bail is the rule</mark>" in out


def test_status_badge_known():
    assert "verified" in status_badge("verified")
    assert "unsupported" in status_badge("unsupported")
