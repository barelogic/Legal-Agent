# user4 status — local-LLM runtime (readable by all agents)

Owner: user4 · Branch: `ops/local-llm` · Worktree: `/home/frost/legal-agent-local`
Updated: 2026-10-09 — branch + `ops/` + docs landed; dev-split rerun running.

## Step 1 — branch + worktree (done)

- Read `AGENTS.md`, `README.md`, `eval/README.md`, `user1.md`, `user2.md`,
  `user3.md`; ran `git status` + `git branch --show-current` (clean
  `ops/local-llm` before every shared-file touch).
- `git worktree add /home/frost/legal-agent-local -b ops/local-llm origin/main`,
  fast-forwarded to `origin/main e543f4e` (court + HF-legal corpus expansion).
- Added my row to `AGENTS.md`'s table (only shared-file edit).
- Measured: nothing yet at this step. Need from others: nothing.

## Step 2 — `ops/` runtime (done, no frozen edits)

- Created `ops/env.local-llm.example` (loopback Ollama pins; kept out of root
  `.env.example` per `eval/tests/test_prod_gemini.py`), `ops/pull_models.sh`
  (prefetch: `ollama pull` + ST warm + corpus fetch/build),
  `ops/run_local_eval.sh` (refuses non-loopback base / `GEMINI_LIVE_TEST`;
  dev split only, `--hf-limit 0 --top-k 4`),
  `ops/check_local.py` (loopback-guarded smoke, no pipeline import),
  `ops/tests/test_ops_local.py` (+ `__init__.py` pair).
- Measured: `ops/tests/` **3 passed**; `tests/` **130 passed**;
  `contracts/schemas.py` untouched (`git diff` empty).
  Machine: RTX 4060 Laptop 8188 MiB (4185 free), driver 615.71.09.
- Need from others: nothing (no core/eval/UI patch proposed).

## Step 3 — model verification (done, no guessing)

- `ollama list`: only `llama3.1:8b` present (4.9GB).
- `ollama show llama3.1:8b`: arch llama, 8.0B, ctx **131072**,
  embed 4096, quant **Q4_K_M**. Library page
  (https://ollama.com/library/llama3.1) confirms `llama3.1:8b`, 4.9GB, 128K.
- Embeddings: `sentence-transformers 6.1.0`, `torch 2.14.1+cu130`
  CUDA=True, `chromadb 1.5.9`; `BAAI/bge-m3` weights cached in
  `~/.cache/huggingface/hub`. Reranker cached but OFF (8GB budget).
- Everything else: **unverified** (see `docs/local_llm.md`).
- Need from others: nothing.

## Step 4 — live smoke, local (done, dev sample, not a split metric)

- Env `openai_compatible:llama3.1:8b` (Q4_K_M, ctx 131072) →
  `http://localhost:11434/v1`, backend lexical (`Registry.search`,
  seeds registry 3 docs / 3 chunks), top_k=4, machine as above.
- `bail in non-bailable offences?` → retrieved 2, candidates 1,
  **verified 1 / dropped 0**, latency 17477ms (cold).
- `ops/check_local.py` → `ok:true`, tags `["llama3.1:8b"]`.
- Need from others: nothing.

## Step 5 — full dev-split rerun, this branch (running)

- `eval/run_all.py --hf-limit 0 --top-k 4 --corpus registry`
  (seeds registry; `data/processed/` absent in this worktree, 6196-doc build
  deferred to prefetch), `--out /tmp/opencode/local-llm-results/` so `eval/`
  stays untouched. Background shell `sh_11d177529001MVpI51Jp0y1iRp`.
- On landing: paste the 5-system table here with full provenance
  (model/quant/ctx/backend/machine), then run the network-off test and log it.
- Never scores holdout (harness lists holdout qids, excludes them).
- Need from others: user2's refreshed trap max-overlap on the 6196-doc
  corpus before any dense/hybrid claim on big corpus.
