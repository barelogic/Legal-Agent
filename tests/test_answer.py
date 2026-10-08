"""Workflow: grounded answer or explicit refusal (never guess)."""

from pathlib import Path

from generation.llm import MockClient
from ingest.seed import load_seeds
from workflows.answer import REFUSAL, answer_question


def _reg():
    root = Path(__file__).resolve().parent.parent
    return load_seeds(root / "data")


def test_grounded_answer():
    reg = _reg()
    ans = answer_question("When is bail granted in non-bailable offences?", "chat", reg, MockClient(), top_k=4)
    assert not ans.refused
    assert "[c1]" in ans.text
    assert all(c.doc_id in reg.docs for c in [reg.chunks[cid] for cl in ans.claims if cl.status == "verified" for cid in cl.chunk_ids])
    assert ans.citations and all(c.resolved for c in ans.citations)


def test_refusal_on_no_evidence():
    reg = _reg()
    ans = answer_question("xyzzy quantum torts on Mars", "research", reg, MockClient(), top_k=4)
    assert ans.refused
    assert ans.text == REFUSAL


def test_fabricated_claim_dropped():
    from generation.claims import parse_claims
    from verify.verifier import verify_all

    reg = _reg()
    chunks = reg.search("bail non-bailable", top_k=1)
    assert chunks  # multi-token query clears the min-overlap gate
    cmap = {c.chunk_id: c for c in chunks}
    bad = parse_claims('[{"text": "The moon grants bail.", "chunk_ids": ["%s"], "quote": "totally invented"}]' % chunks[0].chunk_id)
    v, f = verify_all(bad, cmap)
    assert v == [] and len(f) == 1
