"""API: health + grounded answer + refusal path."""

import os

os.environ["LLM_PROVIDER"] = "mock"

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"]


def test_answer_grounded():
    r = client.post("/answer", json={"question": "bail in non-bailable offences?", "workflow": "chat"})
    assert r.status_code == 200
    body = r.json()
    assert not body["refused"]
    assert "[c1]" in body["text"]


def test_answer_refuses():
    # zero-overlap probe (verified absent from the corpus vocab): must refuse
    # with seeds alone AND with the full bail corpus built.
    r = client.post("/answer", json={"question": "zxqv wugbench florpnik", "workflow": "chat"})
    assert r.status_code == 200
    assert r.json()["text"] == "Not found in the provided sources"


def test_source_hit_and_miss():
    r = client.get("/sources/bnss_2023::p1::c0")
    assert r.status_code == 200
    assert r.json()["chunk_id"] == "bnss_2023::p1::c0"
    assert client.get("/sources/nope::p9::c9").status_code == 404


def test_top_k_validated():
    assert client.post("/answer", json={"question": "bail?", "top_k": 0}).status_code == 422
    assert client.post("/answer", json={"question": "bail?", "top_k": 51}).status_code == 422
    assert client.post("/answer", json={"question": "bail?", "top_k": 2}).status_code == 200


def test_missing_key_is_503(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    r = client.post("/answer", json={"question": "bail?", "workflow": "chat"})
    assert r.status_code == 503


def test_hybrid_fallthrough_recorded(monkeypatch):
    import api.main as m

    def _boom(*a, **k):
        raise RuntimeError("index gone")

    monkeypatch.setattr(m, "retrieve", _boom)
    r = client.post(
        "/answer",
        json={"question": "bail in non-bailable offences?", "doc_ids": ["bnss_2023"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["trace"]["backend"] == "lexical"
    assert "hybrid failed" in body["trace"]["fallback"]
    assert any("hybrid failed" in f for f in body["trace"]["fallbacks"])
