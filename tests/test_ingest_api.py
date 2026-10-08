"""API ingest: upload -> chunks registered; invalid inputs rejected."""

import os

os.environ["LLM_PROVIDER"] = "mock"

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.main as main

client = TestClient(main.app)
DOC_ID = "api_upload_probe"


@pytest.fixture()
def purge_probe():
    root = Path(main.__file__).resolve().parent.parent
    yield
    reg = main.REGISTRY
    reg.chunks = {cid: c for cid, c in reg.chunks.items() if c.doc_id != DOC_ID}
    reg.docs.pop(DOC_ID, None)
    for name in ("docs.jsonl", "chunks.jsonl"):
        p = root / "data" / "processed" / name
        if p.is_file():
            p.write_text(
                "".join(l for l in p.read_text().splitlines(keepends=True)
                        if f'"{DOC_ID}"' not in l)
            )
    up = main.UPLOAD_DIR / f"{DOC_ID}.txt"
    if up.is_file():
        up.unlink()


def test_ingest_txt(purge_probe):
    r = client.post(
        "/ingest",
        files={"file": (f"{DOC_ID}.txt", b"Section 9 Probe bail text. It applies here.", "text/plain")},
        data={"doc_type": "statute"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["doc"]["doc_id"] == DOC_ID
    assert body["num_chunks"] >= 1
    doc_ids = [d["doc_id"] for d in client.get("/documents").json()["docs"]]
    assert DOC_ID in doc_ids
    # newly ingested text is answerable through the grounded pipeline
    a = client.post("/answer", json={"question": "probe bail text?", "doc_ids": [DOC_ID]})
    assert a.status_code == 200 and not a.json()["refused"]


def test_ingest_bad_doctype():
    r = client.post(
        "/ingest",
        files={"file": ("x.txt", b"hi", "text/plain")},
        data={"doc_type": "blog"},
    )
    assert r.status_code == 422


def test_ingest_bad_suffix():
    r = client.post(
        "/ingest",
        files={"file": ("x.exe", b"hi", "application/octet-stream")},
        data={"doc_type": "statute"},
    )
    assert r.status_code == 422
