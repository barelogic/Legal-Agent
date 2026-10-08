from pydantic import BaseModel
from typing import Literal, Optional

class Doc(BaseModel):
    doc_id: str                      # stable slug, e.g. "bnss_2023", "sc_2022_xyz"
    title: str
    doc_type: Literal["statute", "judgment", "case_file"]
    citation: Optional[str] = None   # canonical citation string if any
    source_url: Optional[str] = None
    year: Optional[int] = None

class Chunk(BaseModel):
    chunk_id: str                    # "{doc_id}::p{page}::c{n}"
    doc_id: str
    section_label: Optional[str] = None   # "Section 483", "Para 14"
    page: Optional[int] = None
    text: str

class Claim(BaseModel):
    claim_id: str                    # "c1", "c2", ...
    text: str                        # one atomic factual statement
    chunk_ids: list[str]             # supporting chunks
    quote: str                       # verbatim span from a cited chunk
    status: Literal["unverified", "verified", "unsupported", "removed"] = "unverified"
    verifier_note: Optional[str] = None

class Citation(BaseModel):
    cite_id: str
    raw: str                         # exactly as written in the output
    doc_id: Optional[str] = None     # resolved registry entry, None = unresolved
    resolved: bool = False

class MissingInfo(BaseModel):
    field: str                       # e.g. "FIR number"
    why_needed: str
    searched_in: list[str] = []      # doc_ids checked

class Contradiction(BaseModel):
    description: str
    claim_a: str                     # chunk_id
    claim_b: str                     # chunk_id

class Answer(BaseModel):
    workflow: Literal["chat", "draft", "review", "research"]
    text: str                        # rendered output, claims marked [c1][c2]
    claims: list[Claim]
    citations: list[Citation]
    missing_info: list[MissingInfo] = []
    contradictions: list[Contradiction] = []
    confidence: Optional[float] = None
    refused: bool = False
    refusal_reason: Optional[str] = None
    trace: dict = {}                 # timings, retrieved chunk_ids, for debugging
