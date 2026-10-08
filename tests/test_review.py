"""Review workflow: verified key facts + deterministic contradictions.

P2's planted-conflict case files do not exist in this tree, so the
conflicts are planted inline here (same shapes: shared FIR, conflicting
arrest date, one doc missing its medical report).
"""

from contracts.schemas import Chunk, Doc
from generation.llm import MockClient
from retrieval.store import Registry
from workflows.review import extract_attribute_values, find_contradictions, run_review

A_CHUNKS = [
    "FIR number 0451/2024 was registered at Kotwali station.",
    "Ravi Kumar was arrested, date of arrest 12-03-2024.",
    "Charge sheet was filed after investigation.",
    "Remand order was passed by the magistrate.",
    "Medical report of the complainant is on record.",
]
B_CHUNKS = [
    "FIR number 0451/2024 was registered at Kotwali station.",
    "Ravi Kumar was arrested, date of arrest 14-03-2024.",
    "Charge sheet was filed after investigation.",
    "The magistrate passed the remand order.",
]


def _reg() -> Registry:
    reg = Registry()
    for doc_id, texts in (("caseA", A_CHUNKS), ("caseB", B_CHUNKS)):
        reg.register_doc(Doc(doc_id=doc_id, title=doc_id, doc_type="case_file"))
        for i, t in enumerate(texts):
            cid = f"{doc_id}::p1::c{i}"
            reg.chunks[cid] = Chunk(chunk_id=cid, doc_id=doc_id, text=t)
    return reg


def test_review_facts_and_conflict():
    reg = _reg()
    ans = run_review(doc_ids=["caseA", "caseB"], registry=reg, llm=MockClient())
    assert not ans.refused
    assert all(c.status == "verified" for c in ans.claims)
    assert "## caseA" in ans.text and "## caseB" in ans.text
    assert len(ans.contradictions) == 1
    contra = ans.contradictions[0]
    assert "date of arrest" in contra.description
    assert "12-03-2024" in contra.description and "14-03-2024" in contra.description
    assert contra.claim_a in reg.chunks and contra.claim_b in reg.chunks
    # Shared FIR number must NOT contradict.
    assert not [c for c in ans.contradictions if "FIR" in c.description]


def test_missing_medical_report():
    ans = run_review(doc_ids=["caseA", "caseB"], registry=_reg(), llm=MockClient())
    missing = [(m.field, m.searched_in) for m in ans.missing_info]
    assert ("medical report", ["caseB"]) in missing
    assert not [m for m in ans.missing_info if m.field == "medical report" and m.searched_in == ["caseA"]]


def test_unknown_doc_yields_missing():
    ans = run_review(doc_ids=["ghost"], registry=_reg(), llm=MockClient())
    assert ans.refused
    assert any(m.field == "ghost" for m in ans.missing_info)


def test_extractors_conservative():
    # Bare "FIR registered" with no digits is not an FIR number.
    assert not [p for p in extract_attribute_values("FIR was registered yesterday") if p[0] == "FIR number"]
    # A section without an Act stays in its own conservative bucket.
    attrs = extract_attribute_values("Section 483 applies here.")
    assert attrs and attrs[0][0] == "section (act unspecified)"
    # Same attribute, same value, different docs: no contradiction.
    from contracts.schemas import Claim
    cs = [
        Claim(claim_id="c1", text="FIR number 0451/2024 was registered.", chunk_ids=["caseA::p1::c0"], quote="q"),
        Claim(claim_id="c2", text="FIR number 0451/2024 was registered.", chunk_ids=["caseB::p1::c0"], quote="q"),
    ]
    assert find_contradictions(cs) == []
