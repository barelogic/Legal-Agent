"""FastAPI entrypoint: grounded legal assistant (refuse-by-default)."""

import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from contracts.schemas import Answer, Chunk
from generation.llm import make_client
from ingest.hf_cases import ingest_hf
from ingest.pipeline import DOC_TYPES, SUFFIXES, ingest_file, load_chunks, load_docs
from ingest.seed import load_seeds
from retrieval.hybrid import rebuild_index
from workflows.flags import run

app = FastAPI(title="Legal Agent (grounded)")


def _registry():
    # data/ lives next to repo root: <root>/data ; this file is <root>/api/main.py
    root = Path(__file__).resolve().parent.parent
    reg = load_seeds(root / "data")
    for doc in load_docs():  # ingested files upsert over seeds on doc_id collision
        reg.chunks = {cid: c for cid, c in reg.chunks.items() if c.doc_id != doc.doc_id}
        reg.register_doc(doc)
    for chunk in load_chunks():
        if chunk.doc_id in reg.docs:
            reg.chunks[chunk.chunk_id] = chunk
    return reg


REGISTRY = _registry()
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"


class AskIn(BaseModel):
    question: str
    workflow: Literal["chat", "draft", "review", "research"] = "chat"
    top_k: int | None = None
    doc_ids: list[str] | None = None
    # I1: optional per-request flag overrides (None = server default).
    # Backward compatible: absent fields behave exactly as before.
    verify_text: bool | None = None
    entailment: bool | None = None
    citation_gate: bool | None = None
    regenerate: bool | None = None
    coverage: bool | None = None
    rerank: bool | None = None
    short_boost: bool | None = None


class HfIn(BaseModel):
    limit: int = 50
    disposition: str | None = None
    court: str | None = None


@app.get("/health")
def health() -> dict:
    return {"ok": True, "docs": len(REGISTRY.docs), "chunks": len(REGISTRY.chunks)}


@app.get("/documents")
def list_docs() -> dict:
    return {"docs": [d.model_dump() for d in REGISTRY.docs.values()]}


@app.get("/sources/{chunk_id}", response_model=Chunk)
def get_source(chunk_id: str) -> Chunk:
    """Serve one stored chunk verbatim (read-only; UI source view)."""
    chunk = REGISTRY.chunks.get(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="unknown chunk_id")
    return chunk


@app.post("/answer", response_model=Answer)
def post_answer(body: AskIn) -> Answer:
    """Grounded answer: same run() entry the eval harness uses."""
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    if body.top_k is not None and not 1 <= body.top_k <= 50:
        raise HTTPException(status_code=422, detail="top_k must be 1..50")
    try:
        llm = make_client()  # generate_claims binds retrieved chunks for mock
    except RuntimeError as e:
        # Missing API key / bad provider config: server-side, not a bad query.
        raise HTTPException(status_code=503, detail=str(e))
    try:
        return run(body.workflow, body, registry=REGISTRY, llm=llm)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM/retrieval failed: {e}")


@app.post("/ingest")
def post_ingest(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
) -> dict:
    """Upload a .pdf/.txt file, parse into section-aware chunks, register them."""
    if doc_type not in DOC_TYPES:
        raise HTTPException(status_code=422, detail=f"doc_type must be one of {DOC_TYPES}")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUFFIXES:
        raise HTTPException(status_code=422, detail=f"only {list(SUFFIXES)} uploads")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / Path(file.filename or "upload").name
    dest.write_bytes(file.file.read())
    try:
        doc, chunks = ingest_file(dest, doc_type)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    REGISTRY.chunks = {
        cid: c for cid, c in REGISTRY.chunks.items() if c.doc_id != doc.doc_id
    }
    REGISTRY.register_doc(doc)
    for c in chunks:
        REGISTRY.chunks[c.chunk_id] = c
    try:
        rebuild_index()
    except Exception as e:
        # Best-effort: lexical registry already updated; surface, don't swallow.
        note = f"hybrid index rebuild failed: {e}"
        logger.warning("ingest: %s", note)
        resp = {
            "doc": doc.model_dump(),
            "num_chunks": len(chunks),
            "chunk_ids": [c.chunk_id for c in chunks],
            "index_note": note,
        }
        return resp
    return {
        "doc": doc.model_dump(),
        "num_chunks": len(chunks),
        "chunk_ids": [c.chunk_id for c in chunks],
    }


@app.post("/ingest/hf")
def post_ingest_hf(body: HfIn) -> dict:
    """Stream rows from Sumitedu/indian-case-laws into Docs + Chunks."""
    if body.limit < 1 or body.limit > 5000:
        raise HTTPException(status_code=422, detail="limit must be 1..5000")
    try:
        docs, chunks = ingest_hf(
            limit=body.limit, disposition=body.disposition, court=body.court
        )
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    for doc in docs:
        REGISTRY.chunks = {
            cid: c for cid, c in REGISTRY.chunks.items() if c.doc_id != doc.doc_id
        }
        REGISTRY.register_doc(doc)
    for c in chunks:
        REGISTRY.chunks[c.chunk_id] = c
    try:
        rebuild_index()
    except Exception as e:
        # Best-effort: registry already updated; surface, don't swallow.
        note = f"hybrid index rebuild failed: {e}"
        logger.warning("ingest/hf: %s", note)
        return {
            "num_docs": len(docs),
            "num_chunks": len(chunks),
            "doc_ids": [d.doc_id for d in docs],
            "index_note": note,
        }
    return {
        "num_docs": len(docs),
        "num_chunks": len(chunks),
        "doc_ids": [d.doc_id for d in docs],
    }
