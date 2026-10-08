"""E4 workflow-metrics tests (mock-pinned, no network/LLM calls)."""

import os

os.environ["LLM_PROVIDER"] = "mock"

import sys

sys.path.insert(0, ".")

from contracts.schemas import Answer, Citation, Claim, MissingInfo
from eval.workflow_metrics import (GOLD, detector_unit_check, draft_metrics,
                                   planted_docs, research_metrics,
                                   review_metrics)


def _ans(**kw):
    base = {"workflow": "chat", "text": "t", "claims": [], "citations": [],
            "trace": {}}
    base.update(kw)
    return Answer(**base)


def test_detector_unit_exact():
    d = detector_unit_check()
    assert d["precision"] == 1.0 and d["recall"] == 1.0


def test_planted_docs_conflict_shape():
    _, ca, _, cb = planted_docs()
    assert "0451/2024" in ca.text and "0451/2024" in cb.text
    assert "50,000" in ca.text and "75,000" in cb.text


def test_draft_metrics_hand_answer():
    reg_docs = {"d1"}
    c1 = Claim(claim_id="c1", text="Vikas Sharma is the applicant",
               chunk_ids=["d1::p1::c1"], quote="applicant Vikas Sharma",
               status="verified")
    ch = {"d1::p1::c1": "the applicant Vikas Sharma appeared today"}
    c1 = c1.model_copy(update={"quote": "applicant Vikas Sharma"})
    ans = _ans(workflow="draft", claims=[c1],
               citations=[Citation(cite_id="d1", raw="d1", doc_id="d1",
                                   resolved=True)],
               missing_info=[MissingInfo(field="court", why_needed="x",
                                         searched_in=[])],
               trace={"sourced_fields": ["applicant_name"],
                      "missing_fields": ["court"]})

    class R:
        docs = {"d1": True}
        chunks = {"d1::p1::c1": type("C", (), {"text": ch["d1::p1::c1"]})()}

    m = draft_metrics(ans, R())
    assert m["field_fill_precision"] == 1.0
    assert m["fabrication_in_draft"] == 0
    assert set(GOLD) >= {"applicant_name", "fir_number"}


def test_review_and_research_metrics():
    from contracts.schemas import Contradiction

    r = review_metrics(_ans(contradictions=[
        Contradiction(description="surety amount: 'Rs. 50,000' in a vs 'Rs. 75,000' in b",
                      claim_a="x", claim_b="y")]),
        {"surety amount", "date of arrest"})
    assert r["precision"] == 1.0 and r["recall"] == 0.5
    m = research_metrics([_ans(citations=[Citation(
        cite_id="d", raw="d", doc_id="d", resolved=True)])])
    assert m["citation_resolution_rate"] == 1.0
