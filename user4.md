# user4 status — local-LLM runtime (readable by all agents)

Owner: user4 · Branch: `ops/local-llm` · Worktree: `/home/frost/legal-agent-local`
Updated: 2026-10-09 — dev-split rerun landed (fab 0 verified), network-off test passed.

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

## Step 5 — full dev-split rerun, this branch (landed)

- `eval/run_all.py --hf-limit 0 --top-k 4 --corpus registry`
  (seeds registry; `data/processed/` absent in this worktree, 6196-doc build
  deferred to prefetch), `--out /tmp/opencode/local-llm-results/` so `eval/`
  stays untouched. Background shell `sh_11d177529001MVpI51Jp0y1iRp`.
- 01:36 check: run still alive (PID 193494, 9 min elapsed / ~20s CPU —
  waiting on local generations); resident model serving ctx 4096 noted in
  `docs/local_llm.md`.
- On landing: paste the 5-system table here with full provenance
  (model/quant/ctx/backend/machine), then run the network-off test and log it.
- LANDED 2026-10-09 (gold n=6, 3 answerable; trap n=3):
  `full_lexical_verified` grounded 1.000, fab 0, trap_ref_R 1.000, 11943ms;
  `baseline_no_verify` fab 0, trap 1.000, 5726ms;
  `hybrid_verified` fab 0, trap 1.000, 8410ms;
  `baseline_injected` fab 5 (0.833), trap 0.333;
  `baseline_plain_rag` grounded 0.933, fab 3 (0.500), trap 0.333, 9865ms.
  Config: `openai_compatible:llama3.1:8b`, Q4_K_M, serving ctx 4096 /
  max 131072, lexical (+HybridIndex BM25 leg), judge deterministic-fallback,
  zero `mock-fallback` in `metrics.json`, RTX 4060 Laptop 8GB. Full table in
  `docs/local_llm.md`. Caveat: toy corpus (retrieval 1.000 everywhere);
  ranking matches user2's 47-doc table.
- Never scores holdout (harness lists holdout qids, excludes them).
- Need from others: user2's refreshed trap max-overlap on the 6196-doc
  corpus before any dense/hybrid claim on big corpus.

## Step 6 — network-off test (done)

- `nmcli networking off`: `ops/check_local.py` → `ok:true`
  (`llama3.1:8b` present); live smoke → 1 candidate, verified 1 / dropped 0,
  19631ms. Fully local, zero network. Networking restored (`enabled`).
- Need from others: nothing. Venue prefetch = `bash ops/pull_models.sh`
  (network ON) then this test repeats on the day.

## Step 7 — U1 chunk-ID truncation (reproduced, patches handed to user1)

- Probe (synthetic 4-chunk, realistic long IDs, live
  `openai_compatible:llama3.1:8b`, Q4_K_M, serving ctx 4096, RTX 4060 8GB):
  **0/4 exact** — model emitted the bare doc_id in all 4 claims
  (`ic_the_bharatiya_nagarik_suraksha_s_s478`,
  `hc_brhc_2020_crlmisc_sexbri_00123456`, `statute_bnss_2023`,
  `sc_2024INSC735`), dropping every `::pN::cM` suffix (48.5s).
- Same probe + appended fidelity hint ("copy chunk_ids EXACTLY ... full
  `::pN::cM` suffix ... shortened ID fails verification"), 2-chunk shape:
  **2/2 exact** (47.9s). Direction works; chunk-count confound noted.
- Sequel: verifier drops all 4 baseline claims (`unknown chunk_ids`) → honest
  refusal, no fabrication. Nothing of mine to change (prompt + verifier are
  user1-owned); exact patches below, NOT applied here.

### PATCH U1-A (user1: `generation/claims.py`, prompt fidelity)

```diff
 Rules: quote must be an exact substring of one cited chunk; every number, date, section, amount, name, or citation in text must appear in quote; chunk_ids must come from SOURCES; if the answer is not in SOURCES, output [].
+Rules (IDs): copy each chunk_id EXACTLY as shown in SOURCES, including the full ::pN::cM suffix. Never shorten, truncate, or strip any part of an ID; a shortened ID fails verification.
```

### PATCH U1-B (user1: `verify/verifier.py`, doc-prefix repair)

Insert between the `missing` computation and the `if missing:` fail in
`verify_claim` (verbatim guarantee preserved — repair only selects WHICH
retrieved chunk the quote is checked against; ambiguity still fails):

```diff
     missing = [cid for cid in claim.chunk_ids if cid not in chunk_map]
     if missing:
-        return claim.model_copy(update={
-            "status": "unsupported",
-            "verifier_note": f"unknown chunk_ids: {missing}",
-        })
+        # Doc-id repair for local LLMs that strip the ::pN::cM suffix
+        # (measured user4 2026-10-09: llama3.1:8b 0/4 exact without hint).
+        qnorm = _norm(claim.quote)
+        repaired: list[str] = []
+        unrepaired: list[str] = []
+        for cid in claim.chunk_ids:
+            if cid in chunk_map:
+                repaired.append(cid)
+                continue
+            cands = [k for k in chunk_map if k.startswith(cid + "::")]
+            hits = [k for k in cands if qnorm and qnorm in _norm(chunk_map[k].text)]
+            if len(hits) == 1:
+                repaired.append(hits[0])
+            else:
+                unrepaired.append(cid)
+        if unrepaired:
+            return claim.model_copy(update={
+                "status": "unsupported",
+                "verifier_note": f"unknown chunk_ids: {unrepaired}",
+            })
+        claim = claim.model_copy(update={"chunk_ids": repaired})
```

## Step 8 — U2 60s timeout (reproduced, patch handed to user1)

- Measured: 4-chunk long-ID prompt + hint → `ReadTimeout` at exactly 60s
  (`generation/llm.py:109`, hardcoded `timeout=60`; Gemini leg `:75` same).
  2-chunk ≈48s; seeds top_k=4 ≈17–19s (short chunks). Latency scales with
  prompt length; the fixed 60s is the flake source, not the model.
- Ops-side mitigation (applied): venue default stays truthful — no silent
  `TOP_K` cut (would break eval comparability); `EMBED_DEVICE=cpu` pinned in
  `ops/env.local-llm.example` (measured OOM, core env since `25de873`).

### PATCH U2-C (user1: `generation/config.py` + `generation/llm.py`)

```diff
 # config.py, after get_llm_judge_model:
+def get_llm_timeout(default: int = 60) -> int:
+    """HTTP timeout (s) for LLM calls. Local 8B needs headroom; default 60."""
+    try:
+        return int(os.getenv("LLM_TIMEOUT", str(default)))
+    except ValueError:
+        return default
 # llm.py, top imports:
+from generation.config import get_llm_timeout
 # llm.py, both call sites (Gemini :75, OpenAI-compatible :109):
-        r = requests.post(url, json=body, timeout=60)
+        r = requests.post(url, json=body, timeout=get_llm_timeout())
             ...
-            timeout=60,
+            timeout=get_llm_timeout(),
```
- Then venue `.env` sets `LLM_TIMEOUT=180` (my `ops/env.local-llm.example`
  carries it commented until this lands). Needs from user1: apply U1-A/B +
  U2-C (or counter-propose); needs from others: nothing further.

