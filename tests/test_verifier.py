"""Verifier: verbatim quote + known chunk required."""

from contracts.schemas import Chunk, Claim
from verify.verifier import verify_all, verify_claim


def _map() -> dict[str, Chunk]:
    return {"d::p1::c0": Chunk(chunk_id="d::p1::c0", doc_id="d", text="Bail is the rule.")}


def test_verified():
    c = Claim(claim_id="c1", text="t", chunk_ids=["d::p1::c0"], quote="Bail is the rule.")
    assert verify_claim(c, _map()).status == "verified"


def test_fabricated_quote():
    c = Claim(claim_id="c1", text="t", chunk_ids=["d::p1::c0"], quote="invented statute")
    v = verify_claim(c, _map())
    assert v.status == "unsupported"


def test_unknown_chunk():
    c = Claim(claim_id="c1", text="t", chunk_ids=["nope"], quote="Bail is the rule.")
    assert verify_claim(c, _map()).status == "unsupported"


def test_verify_all_splits():
    ok = Claim(claim_id="c1", text="t", chunk_ids=["d::p1::c0"], quote="Bail is the rule.")
    bad = Claim(claim_id="c2", text="t", chunk_ids=["d::p1::c0"], quote="made up")
    v, f = verify_all([ok, bad], _map())
    assert len(v) == 1 and len(f) == 1
