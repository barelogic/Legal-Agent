"""Draft workflow: template fields sourced only from verified claims."""

import json

import pytest

from contracts.schemas import Chunk, Doc
from generation.llm import MockClient
from retrieval.store import Registry
from workflows.draft import load_template, run_draft

TEMPLATE = {
    "template_id": "test_bail",
    "title": "Test Bail Application",
    "required_fields": [
        {"name": "court", "field_type": "string", "required": True,
         "typically_found_in": "user_input", "description": "Court seized of the matter."},
        {"name": "applicant_name", "field_type": "string", "required": True,
         "typically_found_in": "case_file", "description": "Full name of the accused applicant."},
        {"name": "fir_number", "field_type": "string", "required": True,
         "typically_found_in": "case_file", "description": "FIR number."},
        {"name": "bail_provision", "field_type": "string", "required": True,
         "typically_found_in": "statute", "description": "Bail provision relied upon."},
        {"name": "grounds_for_bail", "field_type": "list_string", "required": True,
         "typically_found_in": "case_file", "description": "Grounds relied upon for bail."},
    ],
    "boilerplate_structure": [
        {"order": 1, "section": "cause_title",
         "fixed_text": "In the court of {court}: {applicant_name} seeks bail in {fir_number}.",
         "placeholders": ["court", "applicant_name", "fir_number"]},
        {"order": 2, "section": "grounds",
         "fixed_text": "Grounds: {grounds_for_bail} under provision {bail_provision}.",
         "placeholders": ["grounds_for_bail", "bail_provision"]},
    ],
}

CASE_CHUNKS = [
    "The applicant name is Ravi Kumar, accused in this case.",
    "FIR number 0451/2024 recorded at the police station.",
    "The grounds for bail are cooperation with investigation.",
]
STATUTE_CHUNKS = ["Bail provision 483 applies to regular bail pleas."]


def _reg(include_fir: bool = True) -> Registry:
    reg = Registry()
    reg.register_doc(Doc(doc_id="case1", title="Case file 1", doc_type="case_file"))
    reg.register_doc(Doc(doc_id="bnss_2023", title="Bharatiya Nagarik Suraksha Sanhita",
                         doc_type="statute"))
    texts = [c for c in CASE_CHUNKS if include_fir or not c.startswith("FIR number")]
    for i, t in enumerate(texts):
        reg.chunks[f"case1::p1::c{i}"] = Chunk(chunk_id=f"case1::p1::c{i}", doc_id="case1", text=t)
    for i, t in enumerate(STATUTE_CHUNKS):
        reg.chunks[f"bnss_2023::p1::c{i}"] = Chunk(
            chunk_id=f"bnss_2023::p1::c{i}", doc_id="bnss_2023", text=t)
    return reg


@pytest.fixture
def tpl(tmp_path, monkeypatch):
    monkeypatch.setenv("TEMPLATES_DIR", str(tmp_path))
    (tmp_path / "test_bail.json").write_text(json.dumps(TEMPLATE))
    return tmp_path


def test_full_draft_sourced_and_user_provided(tpl):
    ans = run_draft(draft_type="test_bail", doc_ids=["case1"],
                    instructions="seek regular bail",
                    provided_values={"court": "Court of Session"},
                    registry=_reg(), llm=MockClient())
    assert not ans.refused
    assert ans.confidence == 4 / 5  # court is user input; 4 retrieved fields sourced
    assert "[USER-PROVIDED: court=Court of Session]" in ans.text
    assert "[MISSING:" not in ans.text
    assert "483" in ans.text  # section number arrived inside a verified claim
    assert all(c.status == "verified" for c in ans.claims)
    assert all(c.resolved for c in ans.citations)


def test_missing_fir_yields_missing_not_guess(tpl):
    ans = run_draft(draft_type="test_bail", doc_ids=["case1"],
                    provided_values={"court": "Court of Session"},
                    registry=_reg(include_fir=False), llm=MockClient())
    assert not ans.refused
    assert "[MISSING: fir_number]" in ans.text
    assert "0451" not in ans.text  # never guessed
    missing = {m.field: m for m in ans.missing_info}
    assert missing["fir_number"].why_needed == "FIR number."
    assert missing["fir_number"].searched_in == ["case1"]
    assert ans.confidence == 3 / 5


def test_fabricated_claim_never_reaches_draft(tpl):
    import json as _json

    class _Liar:
        def complete_claims(self, prompt: str) -> str:
            return _json.dumps([{
                "text": "Bail provision 999 applies to this case.",
                "chunk_ids": ["bnss_2023::p1::c0"],
                "quote": "Bail provision 483 applies to regular bail pleas.",
            }])

    ans = run_draft(draft_type="test_bail", doc_ids=["case1"],
                    provided_values={"court": "Court of Session"},
                    registry=_reg(), llm=_Liar())
    assert "999" not in ans.text
    assert "[MISSING: bail_provision]" in ans.text


def test_provided_values_not_claims(tpl):
    ans = run_draft(draft_type="test_bail", doc_ids=["case1"],
                    provided_values={"court": "Court of Session"},
                    registry=_reg(), llm=MockClient())
    assert not any("Court of Session" in c.text for c in ans.claims)


def test_precheck_reports_without_draft_text(tpl):
    ans = run_draft(draft_type="test_bail", doc_ids=["case1"],
                    provided_values={}, registry=_reg(), llm=MockClient(),
                    precheck=True)
    assert not ans.refused
    assert ans.text.startswith("Precheck for test_bail: 4/5")
    assert "## " not in ans.text
    assert len(ans.claims) > 0
    assert ans.confidence == 4 / 5
    assert any(m.field == "court" for m in ans.missing_info)


def test_unknown_draft_type_rejected(tpl):
    with pytest.raises(ValueError):
        run_draft(draft_type="nope", doc_ids=["case1"], registry=_reg(), llm=MockClient())


def test_load_template_shape(tpl):
    assert load_template("test_bail")["template_id"] == "test_bail"
    with pytest.raises(ValueError):
        load_template("../evil")


def test_field_query_single_token_proposes(tpl, monkeypatch):
    """System-generated field queries retrieve on one shared token
    ('FIR No. 0789/2026' has no word 'number'); the verifier still decides."""
    from contracts.schemas import Chunk, Doc
    from generation.llm import MockClient
    from retrieval.store import Registry
    from workflows.draft import run_draft

    reg = Registry()
    reg.register_doc(Doc(doc_id="c1", title="C", doc_type="case_file"))
    reg.chunks["c1::p1::c0"] = Chunk(
        chunk_id="c1::p1::c0", doc_id="c1", text="FIR No. 0789/2026 recorded here.")
    ans = run_draft(draft_type="test_bail", doc_ids=["c1"],
                    provided_values={"court": "X"}, registry=reg, llm=MockClient(),
                    precheck=True)
    assert "fir_number" not in {m.field for m in ans.missing_info}
    assert any("0789" in c.text for c in ans.claims)
