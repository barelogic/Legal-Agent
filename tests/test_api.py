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
    r = client.post("/answer", json={"question": "xyzzy quantum torts on Mars frobnication", "workflow": "chat"})
    assert r.status_code == 200
    assert r.json()["text"] == "Not found in the provided sources"


def test_source_hit_and_miss():
    r = client.get("/sources/bnss_2023::p1::c0")
    assert r.status_code == 200
    assert r.json()["chunk_id"] == "bnss_2023::p1::c0"
    assert client.get("/sources/nope::p9::c9").status_code == 404
