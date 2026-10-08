# user1 status — core / phase 1 (readable by all agents)

Owner: user1 (Core phase-1 owner) · Branch: `core/phase-1` · Worktree: `/home/frost/legal-agent-core`
Updated: 2026-10-08, at `bdaae51` (hybrid gate; main at `939d943`, pushed to origin).

## Landed on main (all pushed to origin)

- `8a59c2e` Phase 1 core: ingest (section-aware PDF/txt + JSONL), lexical+hybrid
  retrieval, claims generation, verifier, workflows, FastAPI (`/answer`,
  `/ingest`, `/ingest/hf`, `/documents`). 48 tests green at landing.
- `37b05e7` AGENTS.md: roles, grounding policy, env, pre-commit rules.
- `1ca19fa` AGENTS.md: worktree map + status-check-before-edit protocol
  (work only in your worktree/branch; `git status` + branch check before
  touching shared/tracked files; one shared venv).
- `04d98da` Refusal hardening + `GET /sources/{chunk_id}` (merge `9db7519`):
  zero-overlap probe, `min_overlap=2` gate in `retrieval/store.py`,
  verbatim `Chunk` route (200 / 404), AGENTS.md render rule.
- `bdaae51` Hybrid BM25 leg: same `min_overlap` gate (merge `939d943`).
  Dense leg intentionally untouched — embeddings match paraphrases with zero
  token overlap by design (moot today: dense inert without ML libs).

## Grounding guarantees (pinned by tests, not assumed)

- `contracts/schemas.py` frozen — zero diff, every commit.
- Refusal probe `zxqv wugbench florpnik` verified zero content-token overlap
  against live corpus vocab (6,196 tokens, 43 docs / 1485 chunks).
- `min_overlap=2` (distinct content-tokens; section-label bypass kept):
  zero-overlap → refused, single-token (`quantum`) → refused, genuine bail
  query → answered. Proven on live store for both registry and hybrid paths.
- `GET /sources/{chunk_id}` serves stored chunks verbatim, read-only.
  user3's duplicate `b4747aa` on `ui/streamlit` is byte-identical; auto-resolves.

## Checks (this worktree)

- `pytest tests/`: **52 passed**.
- `contracts/schemas.py`: untouched.
- Live-corpus spot checks: `zxqv…` → 0 hits/refused, `xyzzy quantum…` → 0 hits,
  `bail in non-bailable offences?` → 4 hits/answered.

## Corrections-file fixes (2026-10-08, on `core/phase-1`, merged to main)

Report: `/home/frost/correctionsfile.md` (main @ `a49f55c`). Both core items fixed:

- **Hybrid index dropped seeds**: `_default_chunks()` returned only processed
  JSONL when present. New `_registry_chunks()` unions seeds + processed with
  the exact upsert order of `api/main.py:_registry`; pinned by
  `test_default_chunks_include_seeds`. Repro now passes on the live
  1,485-chunk union: `doc_ids=["case_file_demo"]` → 1 hit, `["bnss_2023"]` → 1 hit.
- **Single-token queries always refused**: gate is now proportional —
  `required = min(min_overlap, #distinct query tokens)` in both `store.py`
  and `hybrid.py`, plus section-label bypass parity in hybrid's TF leg
  (incl. the +3 bonus mirror). `'bail'` → 4 hits/answered; multi-token noise
  sharing one term (`xyzzy quantum frobnication`) → still refused. Verifier
  still decides truth; retrieval only proposes. user2 note: single-token
  traps, if any, will now score as answered — check against your intended
  refusal P/R in `eval/metrics_grounded.py`.

## Verifier hardening (2026-10-08, on `core/phase-1`, unmerged)

Closes the quote-smuggling hole: `verify_claim` checked only that
`quote` is verbatim in a cited chunk while `claim.text` (model-written)
was unchecked. New stages in `verify/verifier.py`, all behind env flags
(`VERIFY_TEXT / VERIFY_ENTAILMENT / VERIFY_CITATION_GATE /
VERIFY_REGENERATE`, default ON — no A3 flag spec found in repo):

- `verify/textcheck.py`: every number/date/section/money/case/court/
  proper-span/acronym in `text` must appear in normalised `quote`
  (verbatim strictness, no fuzzy matching). Single capitalised words and
  stopwords never extracted; `Section`↔`s.` tolerated on number match;
  leading `In/Under/...` stripped from spans (killed one real over-refusal).
- `verify/judge.py`: entailment yes/no/partial at temp 0, only `yes`
  passes; `LLM_JUDGE_MODEL` else unlike generator; skipped under Mock.
- `verify/citations.py`: `resolve_raw` doc_id fallback is word-boundary
  only; `Section N of <Act>` resolves via the Act part; each mention must
  resolve AND appear in quote/chunk.
- `workflows/answer.py`: >30% failed → one retry with failure notes,
  keep-better; `trace` gains `dropped_reasons`, `fallbacks`,
  `verify_flags`, `regenerated` (trace-dict keys only — no API shape
  change, `contracts/schemas.py` untouched).
- `generation/claims.py`: SOURCES marked untrusted data (`<SOURCES>`);
  instruction-like claim text is dropped by the verifier.

False refusals on `eval/queries.jsonl` answerable (seeds-only registry):
**12/30 = 40.0%, byte-identical to pre-change baseline** (all 12 are
empty-retrieval gaps; verifier-caused: none). Suite: **78 passed**.

## Flags for other areas (not mine to fix)

- user2: trap `refusal_R` delta is yours (`eval/results/` regen under gates).
  My read, already logged: `min_overlap=2` only blocks <2-token overlap, so
  multi-token-but-irrelevant traps need a relevance signal or live-LLM `[]`
  — no core change indicated unless your numbers say otherwise.
- user3: nothing blocking from core; `/sources` is live on main. Take the
  `zxqv` probe line at your next merge (10-second manual pick).
- All: `data/processed/` is per-worktree runtime state (gitignored) — rebuild
  via `corpus/build_corpus.py`. Shared venv:
  `/home/frost/legal-agent/.venv/bin/python -m ...`.
