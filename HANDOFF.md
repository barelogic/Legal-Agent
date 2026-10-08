# HANDOFF — core / phase 1 (user1)

Owner: user1 · Branch: `core/phase-1` · Worktree: `/home/frost/legal-agent-core`
Written: 2026-10-08. All commits below are on `core/phase-1` unless marked `main`.

## Where things stand

- `core/phase-1` HEAD: `1c54761` (corrections fixes). Fully merged into `main`
  via `8c46752`; `origin/core/phase-1` is current. **Nothing unmerged.**
- `origin/main` has since advanced to `f8d76d4` (user3's UI corrections fixes).
  Core did not verify that tip — re-run the suite there before trusting it.
- `HANDOFF.md` (this file) is committed **core-branch only**, deliberately
  not merged to `main`. Merge it with the next core change, or leave it here.

## What core delivered (in merge order)

1. `8a59c2e` Phase 1 core: section-aware ingest (PDF/txt → JSONL), lexical +
   hybrid retrieval, structured-claims generation, verbatim-quote verifier,
   `answer_question`/`answer_from_chunks` workflows, FastAPI (`/answer`,
   `/ingest`, `/ingest/hf`, `/documents`). 48 tests green at landing.
2. `37b05e7` AGENTS.md: roles, grounding policy, env, pre-commit rules.
3. `1ca19fa` AGENTS.md: worktree map + status-check-before-edit protocol.
4. `04d98da` → main `9db7519`: refusal hardening + `GET /sources/{chunk_id}`.
   Zero-overlap probe (`zxqv wugbench florpnik`, verified absent from the
   6,196-token live corpus vocab); `min_overlap=2` gate in
   `retrieval/store.py`; verbatim `Chunk` route (200 / 404).
5. `bdaae51` → main `939d943`: same gate on hybrid's BM25 leg. Dense leg
   intentionally ungated (embeddings match zero-token paraphrases by design;
   moot today — dense is inert without ML libs).
6. `c1402b9` `user1.md` status note (mirrors `user2.md`).
7. `1c54761` → main `8c46752`: `/home/frost/correctionsfile.md` core items —
   hybrid `_registry_chunks()` unions seeds + processed (was processed-only,
   so seed `doc_ids` filters refused); gate made proportional
   (`required = min(min_overlap, #distinct query tokens)`) in both paths +
   section-label bypass parity in hybrid (incl. +3 bonus mirror).

## Load-bearing decisions (do not "simplify" without re-verifying)

- `contracts/schemas.py` is frozen — zero diff on every core commit.
- Refusal is layered: retrieval gate (noise) → verifier (false claims) →
  `Not found in the provided sources` when nothing survives. Retrieval only
  proposes; the verifier decides truth.
- Proportional gate rationale: a 1-term query that matches fully is a genuine
  term search; multi-token noise sharing 1 term still refuses. Consequence:
  single-token traps now score as *answered* (flagged to user2).
- `data/processed/` is per-worktree gitignored runtime state. Core tree has
  seeds only; the full 43-doc / 1,485-chunk corpus lives in the main-tree
  data dir. Live checks must point at it explicitly
  (`_registry_chunks('/home/frost/legal-agent')`).
- One shared venv: `/home/frost/legal-agent/.venv/bin/python -m ...`.

## Test state

- Branch: **56 passed** (`tests/`). Main at merge `8c46752`: **66 passed**.
- Pre-commit gate: pytest green + `git diff -- contracts/schemas.py` empty.
- Live proofs used during this session: `doc_ids=["case_file_demo"]` → 1 hit,
  `["bnss_2023"]` → 1 hit, `'bail'` → answered, both noise probes → refused.

## Worktree map (do not checkout another user's branch)

| Who | Worktree | Branch |
|---|---|---|
| user1 (core) | `/home/frost/legal-agent-core` | `core/phase-1` |
| user2 (eval/data) | `/home/frost/legal-agent-eval` | `eval/data-eval` |
| user3 (UI) | `/home/frost/legal-agent` | `ui/streamlit` |
| corrections re-test | `/tmp/opencode/legal-agent-main` | `main` (detached use ok) |

`main` takes merges only. `main` is usually checked out at the corrections
worktree — merge via a detached temp worktree
(`git worktree add --detach /tmp/merge-X origin/main`, merge, test,
`push origin HEAD:main`), then remove it.

## Open items (none blocking core)

- user2: re-check trap refusal P/R under the proportional gate
  (`eval/metrics_grounded.py`); regen `eval/results/` tables.
- user3: UI corrections merged (`f8d76d4`) — core has no further dependency.
- Next core change (if any): merge this `HANDOFF.md` along with it.
