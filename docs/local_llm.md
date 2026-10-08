# Local LLM runtime (branch `ops/local-llm`)

Fully local legal-agent runtime for one RTX 4060 mobile laptop (8GB VRAM):
Ollama for generation, sentence-transformers for embeddings. No cloud calls.
Every fact still traces to a retrieved source; the verifier decides truth.

## How it plugs in (no frozen code changed)

- The pipeline already abstracts the LLM (`generation/llm.py:make_client`):
  `LLM_PROVIDER=openai_compatible` + `OPENAI_BASE_URL=http://localhost:11434/v1`
  routes generation to local Ollama. No edits to `generation/` needed.
- Retrieval already degrades gracefully (`retrieval/hybrid.py`): dense leg
  engages only when `chromadb` + `sentence-transformers` + cached weights are
  present; otherwise BM25/lexical. No edits to `retrieval/` needed.
- Local pins live in `ops/env.local-llm.example` (NOT root `.env.example`:
  `eval/tests/test_prod_gemini.py` forbids committed loopback endpoints
  there). Copy to `.env` (gitignored) for venue runs.
- `ops/run_local_eval.sh` refuses non-loopback bases and any
  `GEMINI_LIVE_TEST`, and only ever scores the dev/tunable split (holdout
  qids listed, never scored by `eval/run_all.py`).

## Verified model inventory (do not guess beyond this)

| Role | Tag | Quant | Context | Backend | Status |
|---|---|---|---|---|---|
| Generator (default) | `llama3.1:8b` | `Q4_K_M` (`ollama show`) | 131072 (`ollama show`; library lists 128K, https://ollama.com/library/llama3.1) | `openai_compatible` → `http://localhost:11434/v1` | VERIFIED (`ollama list` 4.9GB + `ollama show` + library page) |
| Embeddings | `BAAI/bge-m3` | n/a (ST weights) | n/a | `sentence-transformers 6.1.0`, `torch 2.14.1+cu130` CUDA=True, `chromadb 1.5.9` | VERIFIED (present in `~/.cache/huggingface/hub/models--BAAI--bge-m3`) |
| Reranker | `BAAI/bge-reranker-base` | n/a | n/a | OFF on laptop (see below) | VERIFIED cached, intentionally unused |

Anything else (e.g. `qwen2.5:*`, `mistral:*`, `phi*:*`, `gemma*:*`,
`all-MiniLM-L6-v2` as `EMBED_MODEL`): **unverified** — no `ollama pull` +
`ollama show` + library-page check was performed here. Add only with the
same three confirmations and a fresh dev-split measurement.

## VRAM budget (RTX 4060 Laptop, 8188 MiB; 4185 MiB free at smoke time)

- `llama3.1:8b Q4_K_M` ≈ 4.9GB resident — fits with headroom for the API +
  Streamlit on the same box.
- `bge-m3` dense encoding runs on CUDA but the persistent Chroma cache
  (`data/chroma/`, gitignored) means one-time encode; reranker stays OFF
  (`RERANKER_MODEL=` empty) to protect the 8GB budget and demo latency.
- Default demo path is `RETRIEVAL_BACKEND=lexical`; hybrid+dense is opt-in
  per query and falls back honestly (backend logged in `trace["backend"]`).

## Prefetch before the venue (network ON)

```bash
bash ops/pull_models.sh
# - ollama pull llama3.1:8b (+ `ollama show` confirm)
# - ST warm: BAAI/bge-m3 encode on cuda (proves weights cached)
# - corpus raws: fetch_statutes + fetch_judgments --target 20 +
#   fetch_hf_legal + fetch_court_tars (SC2024 + HC sample) +
#   make_case_files + build_corpus.py + eval/build_queries.py (40/40)
```

Bulky raws (`data/raw/sc|hc|hf_legal/`) are gitignored and reproducible;
fetch manifests stay tracked (see `corpus/README.md`).

## Offline test (network OFF, once)

1. Disconnect / `nmcli networking off` (or venue-VPN equivalent).
2. `ollama list` still shows `llama3.1:8b`; `ops/check_local.py` → `ok:true`.
3. `bash ops/run_local_eval.sh` (dev split only) completes with
   `mock-fallback` nowhere in `trace["llm_client"]` (all
   `openai_compatible-live`) and judge `deterministic-fallback`.
4. Streamlit via fixtures still renders (`Use fixtures` toggle, user3).

Status: PENDING — background dev-split run in progress at write time;
network-off rerun queued after it lands.

## Measured numbers (dev split only; never holdout)

Machine for all rows below: RTX 4060 Laptop 8GB, driver 615.71.09.

### This branch, this worktree (seeds registry: 3 docs / 3 chunks)

- Smoke, live (`openai_compatible:llama3.1:8b`, Q4_K_M, ctx 131072,
  backend lexical `Registry.search`, top_k=4):
  `bail in non-bailable offences?` → retrieved 2, candidates 1,
  verified 1 / dropped 0, latency 17477ms (cold model load).
  Single sample, not a split metric — proves the local path end to end.
- Suites: `tests/` **130 passed**; `ops/tests/` **3 passed**;
  `contracts/schemas.py` untouched (`git diff` empty).

### Prior full dev-split reference (NOT mine — user2, `eval/data-eval`)

`eval/run_all.py --hf-limit 0 --top-k 4`, unified 47-doc corpus,
`openai_compatible:llama3.1:8b` live, judge `deterministic-fallback`
(dev/tunable n=30, 25 answerable; see `user2.md` P1 table):

| system | hit_rate | recall@k | mrr | grounded* | fab_count | trap_ref_R | use/5 | lat_ms |
|---|---|---|---|---|---|---|---|---|
| full_lexical_verified | 0.520 | 0.400 | 0.423 | 0.640 | 0 | 0.600 | 2.233 | 5870 |
| baseline_no_verify | 0.520 | 0.400 | 0.423 | 0.840 | 6 | 0.400 | 2.567 | 2964 |
| hybrid_verified | 0.560 | 0.480 | 0.500 | 0.720 | 0 | 0.800 | 2.833 | 2817 |
| baseline_injected (synthetic) | 0.520 | 0.400 | 0.423 | 1.000 | 30 | 0.000 | 2.100 | 3544 |
| baseline_plain_rag | 0.640 | 0.550 | 0.516 | 0.745 | 19 | 0.000 | 2.600 | 2402 |

\*verified_rate (claim pipelines) / mean atomic-claim support (plain RAG).
Reading: the verifier takes pipeline fabrication 6→0
(`baseline_no_verify` vs `full_lexical_verified`); plain RAG retrieves best
but fabricates most (19/30) — usefulness without grounding rewards fluent
hallucination. Model choice is judged by verifier acceptance, hence the
default pipeline stays `full_lexical_verified` on `llama3.1:8b` local.

My own full dev-split rerun on this branch (seeds registry,
`--corpus registry`, out to `/tmp/opencode/local-llm-results/` so `eval/`
stays untouched): RUNNING at write time — table lands in `user4.md` next.

## Patches owed to owners

None. No frozen-dir change was needed (provider switch + env pins suffice).
If the dev-split rerun shows a formatting failure rate worth a prompt tweak,
the exact patch + measured delta goes to user1 (core) — never edited here.

## Needs from others

- user2: refreshed trap max-overlap on the 6196-doc corpus before I score
  dense/hybrid against it (my numbers stay on seeds/unified until then).
- user1: nothing (no core change proposed).
- user3: nothing (UI consumes `Answer` over HTTP; fixtures cover offline).
