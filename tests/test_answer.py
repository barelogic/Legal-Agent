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


def test_refusal_tristate():
    from retrieval.store import Registry
    from contracts.schemas import Chunk, Doc
    from workflows.answer import answer_from_chunks

    doc = Doc(doc_id="d", title="D", doc_type="statute")
    chunk = Chunk(chunk_id="d::p1::c0", doc_id="d", text="Bail is the rule.")
    reg = Registry()
    reg.register_doc(doc)
    reg.chunks[chunk.chunk_id] = chunk

    class _Silent:
        def complete_claims(self, prompt: str) -> str:
            return "[]"

    # (a) nothing retrieved
    a = answer_from_chunks("q?", "chat", reg, _Silent(), [])
    assert a.refused and a.refusal_reason == "no retrieved chunk supported a verifiable claim"
    # (b) evidence present but model silent
    a = answer_from_chunks("q?", "chat", reg, _Silent(), [chunk])
    assert a.refused and a.refusal_reason == "model returned no claims"
    # (c) claims all fail
    class _Bad:
        def complete_claims(self, prompt: str) -> str:
            return '[{"text": "The moon grants bail.", "chunk_ids": ["d::p1::c0"], "quote": "invented"}]'

    a = answer_from_chunks("q?", "chat", reg, _Bad(), [chunk])
    assert a.refused and a.refusal_reason == "all claims failed verification"
    assert a.trace["dropped_reasons"]  # audit trail preserved in trace


def test_missing_info_confidence_and_verified_only():
    from generation.llm import MockClient

    reg = _reg()
    ans = answer_question("When is bail granted in non-bailable offences?", "chat", reg, MockClient(), top_k=4)
    assert not ans.refused
    assert all(c.status == "verified" for c in ans.claims)  # failed stay in trace only
    assert ans.trace["dropped_reasons"] == []  # clean answer drops nothing
    assert ans.trace["dropped"] == 0
    assert ans.confidence == 1.0
    assert ans.contradictions == [] and ans.missing_info == []

    bad = answer_question("xyzzy quantum torts on Mars", "research", reg, MockClient(), top_k=4)
    assert bad.refused and bad.confidence is None
    assert bad.missing_info and bad.missing_info[0].searched_in is not None


def test_regenerate_keeps_better_result():
    import json

    from retrieval.store import Registry
    from contracts.schemas import Chunk, Doc
    from workflows.answer import answer_from_chunks

    doc = Doc(doc_id="d", title="D", doc_type="statute")
    chunk = Chunk(chunk_id="d::p1::c0", doc_id="d",
                  text="The bond shall remain in force for six months.")
    reg = Registry()
    reg.register_doc(doc)
    reg.chunks[chunk.chunk_id] = chunk

    bad = json.dumps([{"text": "The bond lasts for 90 months.",
                        "chunk_ids": [chunk.chunk_id],
                        "quote": "The bond shall remain in force for six months."}])
    good = json.dumps([{"text": "The bond shall remain in force for six months.",
                         "chunk_ids": [chunk.chunk_id],
                         "quote": "The bond shall remain in force for six months."}])

    class _Flaky:
        def __init__(self):
            self.calls = 0

        def complete_claims(self, prompt: str) -> str:
            self.calls += 1
            return bad if self.calls == 1 else good

    llm = _Flaky()
    ans = answer_from_chunks("bond duration?", "chat", reg, llm, [chunk])
    assert llm.calls == 2  # one retry happened
    assert ans.trace["regenerated"] is True
    assert not ans.refused
    assert any(c.status == "verified" for c in ans.claims)


def test_short_query_widens_lexical_net():
    from generation.llm import MockClient
    from retrieval.store import Registry
    from contracts.schemas import Chunk, Doc
    from workflows.answer import SHORT_QUERY_TOP_K, answer_question

    reg = Registry()
    reg.register_doc(Doc(doc_id="d", title="D", doc_type="statute"))
    for i in range(10):
        reg.chunks[f"d::p1::c{i}"] = Chunk(
            chunk_id=f"d::p1::c{i}", doc_id="d", text=f"bail provision note number {i}"
        )
    short = answer_question("bail provision note?", "chat", reg, MockClient(), top_k=4)
    assert short.trace["top_k_effective"] == SHORT_QUERY_TOP_K
    assert "top_k_boost" in short.trace
    assert len(short.trace["retrieved_chunk_ids"]) > 4
    long_q = answer_question(
        "under what detailed circumstances is bail granted in non-bailable offences involving cheating allegations",
        "chat", reg, MockClient(), top_k=4,
    )
    assert long_q.trace["top_k_effective"] == 4
    assert "top_k_boost" not in long_q.trace
