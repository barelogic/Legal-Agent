# Legal Agent — grounded core (hackathon)

Every fact/citation must trace to a retrieved source. One fabricated fact fails us.

## Guarantees
- LLM outputs **structured claims only** (`text, chunk_ids, quote`); final text is
  rendered locally FROM verified claims (`workflows/answer.py:render_text`).
- Verifier (`verify/verifier.py`) requires: cited `chunk_id` exists AND `quote`
  is a verbatim substring of a cited chunk. Failures are **dropped**.
- Empty survival → `Answer(refused=True, text="Not found in the provided sources")`.
- Citations allowed only if they resolve to a `Doc` in the registry
  (`verify/citations.py`). `contracts/schemas.py` is untouched.

## Run (venv)
```bash
python3 -m venv .venv
# bash/zsh:
source .venv/bin/activate
# fish:
source .venv/bin/activate.fish
cp .env.example .env   # LLM_PROVIDER=mock | gemini | openai_compatible
python -m pip install -r requirements.txt
python -m pytest -q              # 44 tests
python -m uvicorn api.main:app --reload
curl -X POST localhost:8000/answer \
  -H 'Content-Type: application/json' \
  -d '{"question":"bail in non-bailable offences?","workflow":"chat"}'
```

## Ingest (`ingest/`)
- `ingest_file(path, doc_type) -> (Doc, list[Chunk])` — `.pdf` via PyMuPDF
  (Tesseract OCR fallback for scanned pages; needs `tesseract-ocr` binary),
  `.txt` direct. Title comes from the filename; citation stays `None`.
- Section-aware chunking (`ingest/chunker.py:chunk_document`): statutes split
  on `Section N`, judgments on numbered paras, case files by page/paragraph.
  Sentence boundaries are never split; `section_label` + `page` preserved.
- Unicode/whitespace canonicalized (`ingest/normalize.py`) so verifier
  quote-matching is reliable; persisted to `data/processed/*.jsonl` (upsert).
- `POST /ingest` (multipart `file` + `doc_type` form field) ingests at runtime.
- `ingest/hf_cases.py` — streams `Sumitedu/indian-case-laws` (17M rows, never
  loaded fully) into `judgment` Docs: doc_id from CNR, citation from the row
  (neutral/law-report/docket fallback), year from `decision_year`.
  `python -m ingest.hf_cases --limit 100 --disposition "BAIL GRANTED"` or
  `POST /ingest/hf {"limit": 50, "disposition": "BAIL GRANTED"}`.
  Heads-up: `indexable_text` is a metadata summary, not the full judgment —
  chunks support case-level facts (court, date, disposition), not deep ratio.

## Retrieval (`retrieval/`)
- `retrieve(query, top_k=8, doc_ids=None) -> list[(Chunk, score)]` — BM25
  (`rank_bm25`) + dense (Chroma, `EMBED_MODEL`, cached in `CHROMA_DIR`) fused
  with reciprocal rank fusion, then cross-encoder rerank (`RERANKER_MODEL`).
- `doc_ids` restricts to case files + statute/judgment corpus as needed.
- Without the ML libs (or offline) it degrades to BM25/lexical — E2E unbroken.
- CLI: `python -m retrieval.search "bail" --top-k 8 --doc-ids bnss_2023`
- `/answer` uses hybrid when `RETRIEVAL_BACKEND=hybrid` or `doc_ids` given.

## Env
`LLM_PROVIDER` (mock default), `LLM_MODEL` (default gemini-2.0-flash),
`GEMINI_API_KEY`/`GOOGLE_API_KEY`, `OPENAI_API_KEY`/`OPENAI_BASE_URL`,
`EMBED_MODEL` (`tfidf-local` = lexical; `BAAI/bge-m3` for dense),
`RERANKER_MODEL`, `CHROMA_DIR`, `RETRIEVAL_BACKEND` (`lexical`|`hybrid`),
`TOP_K` (default 4).
