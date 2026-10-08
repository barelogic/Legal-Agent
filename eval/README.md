# Eval harness — data + evaluation side (branch `eval/data-eval`)

Core pipeline lives in `main` (Phase 1, user1). This dir is additive only:
no edits to `contracts/`, `api/`, `ingest/`, `retrieval/`, `verify/`,
`generation/`, `workflows/`.

## One command (reproduces every number)

```bash
.venv/bin/python eval/run_all.py [--hf-limit 50] [--top-k 4] [--gold-per-doc 2]
# writes eval/results/metrics.json + eval/results/tables.md, prints tables
```

## Design (traceability first)

- `eval/corpus_sources.py` — corpus = seed demos (marked demo, no
  `source_url`) + HF `Sumitedu/indian-case-laws` sample (the dataset given
  to user1; `source_url` = row `source_pdf_s3_url`). The full corpus
  (`corpus/build_corpus.py` → `data/processed/`, 47 docs / 1489 chunks)
  additionally holds 3 MHA bare-Act PDFs, 16 India Code bail sections
  (per-section `source_url`), and 8 `[SYNTHETIC]` case files; see
  `corpus/manifest.json` + `corpus/README.md`. Nothing is faked: every
  statute row carries its official URL.
- `eval/gold.py` — gold queries derived from real chunk text; every
  `answer_span` is a verbatim substring of a gold chunk (stub openers
  extended to >=4 content tokens). Plus unanswerable probes scored as
  refusal recall/precision.
- `eval/systems.py` — 5 systems on `contracts/schemas.py` exactly:
  `full_lexical_verified` (Phase-1 default), `baseline_no_verify` (same
  retriever, verification skipped), `hybrid_verified` (BM25+dense RRF,
  lexical fallback, same verifier), `baseline_injected` (synthetic
  fault-injection stress, always labelled), `baseline_plain_rag`
  (HybridIndex top-5 + one free-text prompt, no claims/verifier; see
  `eval/plain_rag.py`). All honor `LLM_PROVIDER` (mock default identical;
  live via gemini / openai_compatible e.g. local Ollama) and log the
  client in `trace["llm_client"]`.
- `eval/metrics_retrieval.py` — hit_rate / recall@k / MRR (first-relevant
  rank) vs baseline; plain RAG scored at its own top_k=5, logged per system.
- `eval/metrics_grounded.py` — independent quote-exact re-check,
  citation-resolved rate, refusal P/R, fabrication count + rate (rate over
  ALL rows by design: one fabricated claim is a hard fail), trap refusal
  recall (with `trap_def` saying flag vs fallback), mean latency.
- `eval/judge.py` — usefulness 0-5 + entailment (symmetric token-F1, not
  recall). Judge model is `JUDGE_MODEL` (default `gemini-2.5-flash`),
  asserted `!= LLM_MODEL` (default `gemini-2.0-flash`); deterministic
  fallback offline, model logged in every result.
- `eval/ablations.py` — verifier on/off, lexical vs hybrid, top_k {2,4,8};
  deltas (`delta_verifier_fabrication`, `delta_hybrid_recall`) are the
  research contribution.
- `eval/tests/test_eval.py` — offline self-tests (seeds only).
- `eval/queries.jsonl` — 40 hand-built bail-corpus queries (10 each
  chat/review/research/draft; 10 traps with fake cases/missing law, 10
  holdout nobody tunes against). Every answerable `answer_span` is
  verified verbatim against `data/processed/` by `eval/build_queries.py`
  (fails loudly otherwise); gold chunk ids resolve to
  `eval/datasets/queries_resolved.jsonl`; `eval/score_queries.py` scores
  the tunable split and feeds `run_all.py`'s queries table.

## Honest limits (for the write-up)

- Old-law coverage is repeal-rows only (`corpus/section_map.json`); full
  old↔new correspondence needs the official charts (unreachable here).
- HF `indexable_text` is a metadata summary, not full judgments
  (see `ingest/hf_cases.py` note) — case-level facts only.
- Reported numbers use deterministic MockClient + fallback judge unless
  a live LLM is configured (`LLM_PROVIDER` + key/endpoint); the client
  and judge mode are logged in every result (`trace["llm_client"]`,
  `judge_mode`, `plain_rag_llm_mode`).
