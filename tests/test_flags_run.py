"""workflows.flags: unified flags, run() entry, per-flag behaviour flips."""

import pytest

from contracts.schemas import Chunk, Claim, Doc
from generation.llm import MockClient
from retrieval.store import Registry
from workflows.flags import FLAG_NAMES, Flags, flags_from_payload, run


def _reg() -> Registry:
    reg = Registry()
    reg.register_doc(Doc(doc_id="d", title="D", doc_type="statute"))
    reg.chunks["d::p1::c0"] = Chunk(
        chunk_id="d::p1::c0", doc_id="d",
        text="The surety stands in the sum of Rs. 50,000.",
    )
    reg.chunks["d::p1::c1"] = Chunk(
        chunk_id="d::p1::c1", doc_id="d",
        text="In Sharma v. Utopia the court noted bail practice.",
    )
    return reg


def _stub(text: str, quote: str, cid: str):
    import json

    class _S:
        def complete_claims(self, prompt: str) -> str:
            return json.dumps([{"text": text, "chunk_ids": [cid], "quote": quote}])

    return _S()


def test_defaults_all_on(monkeypatch):
    for n in (
        "VERIFY_TEXT", "VERIFY_ENTAILMENT", "VERIFY_CITATION_GATE",
        "VERIFY_REGENERATE", "VERIFY_COVERAGE", "VERIFY_RERANK",
        "VERIFY_SHORT_BOOST",
    ):
        monkeypatch.delenv(n, raising=False)
    f = Flags.from_env()
    assert f.as_dict() == {n: True for n in FLAG_NAMES}


def test_env_kill_switch(monkeypatch):
    monkeypatch.setenv("VERIFY_COVERAGE", "0")
    monkeypatch.setenv("VERIFY_RERANK", "off")
    f = Flags.from_env()
    assert f.coverage is False and f.rerank is False
    assert f.verify_text is True


def test_run_dict_payload_and_trace_flags():
    ans = run("chat", {"question": "What sum stands as surety?", "top_k": 2},
              registry=_reg(), llm=MockClient())
    assert not ans.refused
    assert ans.trace["flags"] == {n: True for n in FLAG_NAMES}
    assert ans.trace["backend"] == "lexical"


def test_run_rejects_bad_input():
    with pytest.raises(ValueError):
        run("chat", {"question": "  "}, registry=_reg(), llm=MockClient())
    with pytest.raises(ValueError):
        run("chat", {"question": "bail?", "top_k": 99}, registry=_reg(), llm=MockClient())


def test_verify_text_flip():
    q = "d::p1::c0"
    llm = _stub(
        "The surety stands in the sum of Rs. 75,000.",
        "The surety stands in the sum of Rs. 50,000.", q,
    )
    payload = {"question": "What sum stands as surety?", "top_k": 4}
    assert run("chat", payload, registry=_reg(), llm=llm).refused
    ans = run("chat", {**payload, "verify_text": False}, registry=_reg(), llm=llm)
    assert not ans.refused
    assert ans.trace["flags"]["verify_text"] is False


def test_citation_gate_flip():
    q = "d::p1::c1"
    llm = _stub(
        "In Sharma v. Utopia the court noted bail.",
        "In Sharma v. Utopia the court noted bail practice.", q,
    )
    payload = {"question": "Sharma Utopia noted bail?", "top_k": 4}
    assert run("chat", payload, registry=_reg(), llm=llm).refused
    assert not run("chat", {**payload, "citation_gate": False},
                   registry=_reg(), llm=llm).refused


def test_entailment_flip():
    from verify.verifier import verify_all

    cmap = {"d::p1::c0": _reg().chunks["d::p1::c0"]}
    claim = Claim(claim_id="c1", text="t", chunk_ids=["d::p1::c0"],
                  quote="The surety stands in the sum of Rs. 50,000.")

    class _Partial:
        def complete_claims(self, prompt: str) -> str:
            return "partial"

    v, f = verify_all([claim], cmap, judge=_Partial(),
                      flagset=Flags().as_dict())
    assert v == [] and len(f) == 1
    v, _ = verify_all([claim], cmap, judge=_Partial(),
                      flagset=Flags(entailment=False).as_dict())
    assert len(v) == 1


def test_regenerate_flip():
    import json

    q = "d::p1::c0"
    bad = json.dumps([{"text": "The bond lasts for 90 months.", "chunk_ids": [q],
                       "quote": "The surety stands in the sum of Rs. 50,000."}])
    good = json.dumps([{"text": "The surety stands.", "chunk_ids": [q],
                        "quote": "The surety stands in the sum of Rs. 50,000."}])

    class _Flaky:
        def __init__(self):
            self.calls = 0

        def complete_claims(self, prompt: str) -> str:
            self.calls += 1
            return bad if self.calls == 1 else good

    payload = {"question": "What sum stands as surety?", "top_k": 4}
    llm = _Flaky()
    ans = run("chat", payload, registry=_reg(), llm=llm)
    assert llm.calls == 2 and not ans.refused
    llm2 = _Flaky()
    ans2 = run("chat", {**payload, "regenerate": False}, registry=_reg(), llm=llm2)
    assert llm2.calls == 1 and ans2.refused


def test_coverage_flip(monkeypatch):
    monkeypatch.setenv("MIN_COVERAGE", "0.9")
    reg = Registry()
    reg.register_doc(Doc(doc_id="d", title="D", doc_type="statute"))
    reg.chunks["d::p1::c0"] = Chunk(
        chunk_id="d::p1::c0", doc_id="d", text="bail provision text here")
    payload = {"question": "bail provision note extra filler", "top_k": 4}
    assert run("chat", payload, registry=reg, llm=MockClient()).refused
    assert not run("chat", {**payload, "coverage": False},
                   registry=reg, llm=MockClient()).refused


def test_rerank_env_flip(monkeypatch):
    import sys
    import types

    import retrieval.hybrid as h

    class _FakeCE:
        def __init__(self, model):
            pass

        def predict(self, pairs):
            return [5.0 if t.endswith(" a") else -5.0 for _, t in pairs]

    fake = types.ModuleType("sentence_transformers")
    fake.CrossEncoder = _FakeCE
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    idx = h.HybridIndex([])
    idx.by_id = {"a": type("C", (), {"text": "x a"})(),
                 "b": type("C", (), {"text": "x b"})()}
    ranked = [("a", 0.1), ("b", 0.09)]
    monkeypatch.delenv("VERIFY_RERANK", raising=False)
    assert [c for c, _ in idx._rerank("q", ranked)] == ["a"]
    monkeypatch.setenv("VERIFY_RERANK", "0")
    assert idx._rerank("q", ranked) == ranked


def test_short_boost_flip():
    from workflows.answer import SHORT_QUERY_TOP_K

    reg = Registry()
    reg.register_doc(Doc(doc_id="d", title="D", doc_type="statute"))
    for i in range(10):
        reg.chunks[f"d::p1::c{i}"] = Chunk(
            chunk_id=f"d::p1::c{i}", doc_id="d",
            text=f"bail provision note number {i}")
    payload = {"question": "bail provision note?", "top_k": 4}
    ans = run("chat", payload, registry=reg, llm=MockClient())
    assert ans.trace["top_k_effective"] == SHORT_QUERY_TOP_K
    ans2 = run("chat", {**payload, "short_boost": False},
               registry=reg, llm=MockClient())
    assert ans2.trace["top_k_effective"] == 4


def test_none_override_inherits():
    base = Flags(coverage=False)
    assert flags_from_payload({"coverage": None}, base).coverage is False
    assert flags_from_payload({"coverage": True}, base).coverage is True
