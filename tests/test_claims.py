"""Claims prompt/parse: JSON-only, bad rows skipped."""

from contracts.schemas import Chunk
from generation.claims import build_prompt, generate_claims, parse_claims
from generation.llm import MockClient


def _ch() -> Chunk:
    return Chunk(chunk_id="d::p1::c0", doc_id="d", text="Bail is the rule and jail is the exception.")


def test_prompt_contains_sources():
    p = build_prompt("q?", [_ch()])
    assert "d::p1::c0" in p and "ONLY" in p


def test_prompt_marks_sources_as_data():
    p = build_prompt("q?", [_ch()])
    assert "untrusted data" in p and "<SOURCES>" in p


def test_parse_ok_and_bad():
    raw = '[{"text": "t", "chunk_ids": ["d::p1::c0"], "quote": "q"}, 42]'
    cs = parse_claims(raw)
    assert len(cs) == 1 and cs[0].claim_id == "c1"


def test_parse_invalid_json():
    assert parse_claims("not json") == []


def test_mock_generates_verbatim_quote():
    cs = generate_claims(MockClient(), "bail?", [_ch()])
    assert cs and cs[0].quote in _ch().text


def test_shared_client_not_mutated():
    from generation.claims import generate_claims
    from generation.llm import MockClient

    sentinel = [Chunk(chunk_id="s::p1::c0", doc_id="s", text="Bail is the rule.")]
    llm = MockClient()
    llm._chunks = sentinel
    generate_claims(llm, "bail?", [_ch()])
    assert llm._chunks is sentinel  # per-call copy takes the binding instead
