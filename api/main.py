"""FastAPI entrypoint: grounded legal assistant (refuse-by-default)."""

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from contracts.schemas import Answer
from generation.config import get_top_k
from generation.llm import make_client
from ingest.hf_cases import ingest_hf
from ingest.pipeline import DOC_TYPES, ingest_file, load_chunks, load_docs
from ingest.seed import load_seeds
from retrieval.hybrid import get_retrieval_backend, rebuild_index, retrieve
from workflows.answer import answer_from_chunks, answer_question

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


@app.post("/answer", response_model=Answer)
def post_answer(body: AskIn) -> Answer:
    """Grounded answer: retrieve -> structured claims -> verify -> render/refuse."""
    if not body.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    top_k = body.top_k or get_top_k()
    llm = make_client()  # generate_claims binds retrieved chunks for mock
    if body.doc_ids or get_retrieval_backend() == "hybrid":
        try:
            hits = retrieve(body.question, top_k=top_k, doc_ids=body.doc_ids)
            return answer_from_chunks(
                body.question, body.workflow, REGISTRY, llm, [c for c, _ in hits]
            )
        except Exception:
            pass  # fall through to lexical registry search
    return answer_question(body.question, body.workflow, REGISTRY, llm, top_k=top_k)


@app.post("/ingest")
def post_ingest(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
) -> dict:
    """Upload a .pdf/.txt file, parse into section-aware chunks, register them."""
    if doc_type not in DOC_TYPES:
        raise HTTPException(status_code=422, detail=f"doc_type must be one of {DOC_TYPES}")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".pdf", ".txt"):
        raise HTTPException(status_code=422, detail="only .pdf and .txt uploads")
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
    except Exception:
        pass  # hybrid index is best-effort; lexical registry already updated
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
    except Exception:
        pass
    return {
        "num_docs": len(docs),
        "num_chunks": len(chunks),
        "doc_ids": [d.doc_id for d in docs],
    }
