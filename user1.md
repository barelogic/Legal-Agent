# user1 status — core / phase 1 (readable by all agents)

Owner: user1 (Core phase-1 owner) · Branch: `core/phase-1` · Worktree: `/home/frost/legal-agent-core`
Updated: 2026-10-09, at `3ac2d8b` (core batch merged to main, pushed to origin).

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
- `3ac2d8b` Core batch (merge `core/phase-1` → main, pushed): verifier
  hardening `0c23f62`, corrections batch 2 `cb2f6c4`, h001 short-query net
  `69c5e9c`, relevance gates `b9b2102`, A3 flags layer `a988cda`,
  B1/B2/B3 workflows `98005fb`, dense-leg fix `25de873`. 165 tests green
  post-merge (124 core + 41 from main).

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

- `pytest tests/`: **165 passed** (124 core + 41 from main, post-merge).
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

## Verifier hardening (2026-10-08, on `core/phase-1`, merged `3bd71b2`, pushed)

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

## Corrections batch 2 (2026-10-08, merged `3ac2d8b`, pushed)

Report: `/home/frost/correctionsfile.md` (full-repo sweep, main @ `d82e17f`).
Decisions taken with user: verified-only `claims` on success (failed stay
in `trace.dropped_reasons`); minimal fill (`missing_info` on refusal with
`searched_in`, `confidence`=verified/total, `contradictions` stays `[]` —
trace-dict/optional fields only, `contracts/schemas.py` untouched).

- Refusal tristate (`no retrieved…` / `model returned no claims` / `all
  claims failed verification`); `claims=verified` on success.
- API: `top_k` 1..50 else 422 (incl. explicit `0`); missing key → 503;
  hybrid failure falls through to lexical with the cause in
  `trace.fallbacks`; both ingest routes surface `index_note` on rebuild
  failure; `backend` recorded in trace. Shared `SUFFIXES` import.
- `claims.py` binds `_chunks` on a per-call copy (race-safe); OpenAI
  malformed payload wrapped as `RuntimeError` like Gemini.
- `hf_cases`: bad year → `None` (no 500); empty CNR+meta → indexed
  `fallback` (no `doc` collisions); `max_scan` documented as scan budget.
- Hybrid label bonus counted once (TF leg `+3` XOR fused `+0.05`);
  `--min-overlap` CLI passthrough; statute headings kept in chunk bodies.
- Dead code: removed zero-caller `get_gemini_key`. KEPT `Registry.get_chunk`
  /`chunk_map` (user3 fixture test calls `fx.get_chunk`) and
  `gate_citations` (their tests import it) — removal would break their tree.
  Dense leg stays ungated by design (flagged before).
- False refusals: **12/30, identical set to baseline**, verifier-caused none.
  Suite: **89 passed** (78 + 11 new).

## Relevance gates (2026-10-08, merged `3ac2d8b`, pushed)

Trap queries share 3-4 content words, which `min_overlap=2` cannot refuse.
New levers, all env-configurable (P2 sweep owns the values; held-out split
never used for tuning):

- `MIN_COVERAGE` (default **0.32**): fraction of distinct query content
  tokens a chunk must contain (lexical + hybrid BM25 legs; explicit
  section-label asks bypass). Default from allowed-split analysis on the
  full 1485-chunk corpus: lowest non-holdout answerable 4/12=0.333 (q025),
  highest separable non-holdout trap 4/13=0.308 (q007). Separates exactly
  one trap — the rest need the reranker, honestly reported, not hidden.
- `RERANK_MIN_SCORE` (default **0.0**, logit sign boundary, pending sweep):
  cross-encoder cutoff in `HybridIndex._rerank`; emptied list refuses
  downstream. Dense leg stays token-ungated by design; this cutoff is its
  only gate (no reranker lib → no gate, as before).
- `api/main.py`: every fallback now sets `Answer.trace.fallback` (singular
  reason) + `logger.warning`; the `fallbacks` list is kept.
- P2 parameter names: `MIN_COVERAGE`, `RERANK_MIN_SCORE`
  (plus existing `VERIFY_*`, `TOP_K`). Env docs in `.env.example`.

## h001 short-query net (2026-10-08, merged `3ac2d8b`, pushed)

Note: `/home/frost/corrections-h001.md` (holdout h001, main @ `c790417`).
Verdict there is "test artifact, no fix required", but the failure mode is
real — a 7-word-prefix question missed its gold chunk in a lexical top-4
(hybrid top-4 had it at rank 1). Fix, not deflection: `answer_question`
widens the lexical net (`top_k` → max 8) when the query has ≤6 distinct
content tokens (`SHORT_QUERY_TOKENS/SHORT_QUERY_TOP_K` in
`workflows/answer.py`; effective value + boost reason in trace). This only
proposes more candidates — gates + verifier still decide, so it cannot
fabricate. Chose this over defaulting everything to hybrid (heavier,
systemic) per the note's own options. Refusals re-measured: **12/30,
identical set**, verifier-caused none. Suite: **90 passed**.

  Correction to the sweep's "fixes landed" note: `max_scan` does NOT count
  kept rows only — it is a scan budget over every streamed row *including*
  skipped ones (see `iter_hf_rows` docstring). Counting kept-only would
  unbind the 17M-row stream; short filtered ingests are the budget working,
  fixed by raising `max_scan`, not by code change.

## A3 flags layer + `run()` entry (2026-10-09, merged `3ac2d8b`, pushed)

Agreements I1/I2 were not in the repo; confirmed with user before building:
I2 = VERIFY_* plus relevance flags, I1 = per-request flag overrides.
`workflows/flags.py` carries all seven flags (verify_text, entailment,
citation_gate, regenerate, coverage, rerank, short_boost — everything on,
each with a `VERIFY_*` env kill-switch) and a shared
`run(workflow, payload, flags=None)` entry that `/answer` and the eval
harness both call; active flags land in `Answer.trace["flags"]`. `AskIn`
gained the seven optional override fields (all `None`-default, backward
compatible). 12 tests prove each flag flips behaviour on a fixed fixture.
`flags.run()` now also dispatches draft/review/research (B1/B2/B3 wiring).

## B1/B2/B3 workflows (2026-10-09, merged `3ac2d8b`, pushed)

- `workflows/draft.py` (B1): per required field — user_input fills render
  `[USER-PROVIDED: field=value]` (never claims) else MissingInfo;
  otherwise scoped retrieval (`Registry.search` gained a backward-compatible
  `doc_ids` filter) with `retrieval_query` or name+description fallback,
  normal claims→verify, sourced only if ≥1 verifies (why_needed=description,
  searched_in=scope). Names containing "provision"/"grounds" also search
  statute+judgment docs; section numbers arrive only inside verified claim
  text. precheck=True returns status text + claims + missing + sourced/required
  confidence, never refused. Full draft assembles boilerplate fixed_text with
  `claim [cN]` / `[MISSING: f]` / `[USER-PROVIDED: …]` fills + Sources block
  (globally renumbered c1..N); refuses only when nothing sourced and no fills.
- `workflows/review.py` (B2): per-doc claims→verify over the doc's own chunks
  (verifier still guards every claim), keyword MissingInfo for FIR / charge
  sheet / remand order / medical report, deterministic regex contradictions
  (FIR-with-digits, attributed dates, Rs.-amounts, named ages, sections) —
  cross-doc pairs only, first-pair-per-(attr,docs), real chunk_ids.
  P2 planted-conflict files are not in this tree, so tests plant inline.
- `workflows/research.py` (B3): case claims (doc_ids scope) + statute/judgment
  claims, citations resolved-only by construction; IPC/CrPC/Evidence mentions
  (±80-char Act window; bare "Section N" skipped) looked up in
  `corpus/section_map.json` — the real file carries repeal rows only, so the
  honest default is MissingInfo ("no verified old-to-new mapping available");
  shown rows must carry source_url (sourceless rows → MissingInfo).
- Wiring: `flags.run()` dispatches draft/review/research (draft/review
  default the question; research requires it); `AskIn` gained optional
  `draft_type/instructions/provided_values/precheck`. Template/map loaders
  read `$TEMPLATES_DIR`/`$SECTION_MAP_PATH` → core paths → main-tree copies
  (read-only; tests use fixtures, suite stays hermetic).
- Suite: **121 passed** (106 + 15 new), schemas untouched.

## Corrections 2026-10-09 pass (on `core/phase-1`, unmerged)

Report: `/home/frost/correctionsfile.md` (fresh pass, main @ `3ac2d8b`).
Two core items, both done here:

- **Judgment routing merged.** Cross-case queries ("which cases was bail
  granted, by which court") refused with `routing: None` because all-statute
  retrieval starved the claims stage. Merged `core/routing-judgment`
  (`ab8e7be`): `doc_routing()` in `retrieval/store.py` (single source of
  truth) flags queries carrying ≥2 outcome/court signals; lexical leg adds
  +3 to judgment-doc chunks, hybrid leg +0.10 post-RRF; `trace["routing"]`
  records it. Gates + verifier unchanged — wider routing only proposes.
  Conflicts were append-append (tests + trace dict); verified the merged
  hybrid hunk (`self.docs` is populated by `get_index()`, guarded falsy in
  bare-index tests). Suite: **175 passed** (171 + 4 temp-0).
- **Temp-0 + recorded policy.** Bailable flakiness is live-LLM sampling, not
  grounding (refusals stay honest). `LLM_TEMPERATURE` (default **0.0**):
  `GeminiClient` now defaults to it (was provider default ~1.0 — the
  flakiness source; OpenAI leg already hardcoded 0 and now honors the env);
  `Answer.trace["llm"]` records provider/model/temperature (mock shows
  `"mock (deterministic)"`). Trace-dict only, schemas untouched.

## Hybrid truth-check (2026-10-09, bge-m3 + reranker on 1485-chunk corpus)

Recall@4 on `eval/datasets/queries_resolved.jsonl` (reported, never tuned;
first run's ~0s were a script bug — wrong gold file — retracted above):

- Non-holdout (n=25): lexical chunk 12/25 (0.48), doc 20/25 (0.80) |
  hybrid-default chunk **20/25 (0.80)**, doc **24/25 (0.96)** |
  hybrid-nogate chunk 21/25 (0.84), doc 24/25 (coverage gate costs 1 hit).
- Holdout (n=5, for completeness): lexical 4/5 chunk, 5/5 doc; hybrid 5/5 both.
- BM25+rerank-only (pre-dense-fix) was chunk 16/25: the dense leg adds +4.
- Traps (n=10): mean retrieved lex 3.1, hyb 4.0 — dense leg is token-ungated
  by design, so it proposes more; refusal stays downstream (verifier+gates).
- Load-bearing bug found by the new warning: `_ensure_dense` called
  `col.get(ids=[c.chunk_id])` with `c` unbound (`NameError`), so the dense
  leg had NEVER engaged — all prior "hybrid" numbers were BM25-only. Fixed
  + regression-tested. Venue: models fine, VRAM is the constraint — set
  `EMBED_DEVICE=cpu` on a busy GPU (embeddings cache in `data/chroma/`).

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
