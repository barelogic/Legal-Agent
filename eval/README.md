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
  to user1; `source_url` = row `source_pdf_s3_url`). No statute text is
  faked: India Code/eSCR are network-blocked here, so `STATUTE_SOURCES`
  stays empty until official fetch works.
- `eval/gold.py` — gold queries derived from real chunk text; every
  `answer_span` is a verbatim substring of a gold chunk. Plus unanswerable
  probes scored as refusal recall/precision.
- `eval/systems.py` — 3 systems on `contracts/schemas.py` exactly:
  `full_lexical_verified` (Phase-1 default), `baseline_no_verify` (same
  retriever, verification skipped), `hybrid_verified` (BM25+dense RRF,
  lexical fallback, same verifier).
- `eval/metrics_retrieval.py` — hit_rate / recall@k / MRR vs baseline.
- `eval/metrics_grounded.py` — independent quote-exact re-check,
  citation-resolved rate, refusal P/R, fabrication rate.
- `eval/judge.py` — usefulness + entailment. Judge model is
  `JUDGE_MODEL` (default `gemini-2.5-flash`), asserted `!= LLM_MODEL`
  (default `gemini-2.0-flash`); deterministic fallback offline, model
  logged in every result.
- `eval/ablations.py` — verifier on/off, lexical vs hybrid, top_k {2,4,8};
  deltas (`delta_verifier_fabrication`, `delta_hybrid_recall`) are the
  research contribution.
- `eval/tests/test_eval.py` — offline self-tests (seeds only).

## Honest limits (for the write-up)

- Statute coverage is demo-only until official fetch succeeds.
- HF `indexable_text` is a metadata summary, not full judgments
  (see `ingest/hf_cases.py` note) — case-level facts only.
- Reported numbers use deterministic MockClient + fallback judge unless
  `GEMINI_API_KEY` is set (then judge mode says `gemini-live`).
