"""Short-query refusal probes (corrections re-check, eval-owned).

Locks the intended refusal P/R after core's proportional gate
(`required = min(min_overlap, len(query content-tokens))`):

- genuine single-token ("bail") MUST answer on seed registry (it fully
  matches; refusing it would tank verified_rate on answerables).
- gibberish single-token ("xyzzy") MUST refuse (no chunk contains it;
  answering it would be fabrication).
- multi-word seed queries MUST answer on both lexical and hybrid paths.
- hybrid `get_index()` MUST include seed docs even when data/processed/
  exists (regression guard for the seed-union fix; eval harness itself
  builds HybridIndex directly so it never skewed, but the API path did).

Offline, deterministic (MockClient via run_system, seeds only).
"""

from eval.corpus_sources import corpus_registry
from eval.systems import run_system


def _seeds():
    return corpus_registry(hf_limit=0)


def test_genuine_single_token_answers():
    docs, chunks = _seeds()
    for sys in ("full_lexical_verified", "hybrid_verified"):
        ans = run_system(sys, "bail", docs, chunks, top_k=4)
        assert not ans.refused, f"{sys} refused genuine single-token 'bail'"
        assert ans.claims, f"{sys} no claims for 'bail'"


def test_gibberish_single_token_refuses():
    docs, chunks = _seeds()
    for sys in ("full_lexical_verified", "hybrid_verified"):
        ans = run_system(sys, "xyzzy", docs, chunks, top_k=4)
        assert ans.refused, f"{sys} answered gibberish single-token 'xyzzy'"


def test_seed_queries_answer_both_paths():
    docs, chunks = _seeds()
    for q in ("FIR 0123/2024 status details", "bail in non-bailable offences?"):
        for sys in ("full_lexical_verified", "hybrid_verified"):
            ans = run_system(sys, q, docs, chunks, top_k=4)
            assert not ans.refused, f"{sys} refused seed query {q!r}"
            assert ans.claims


def test_hybrid_default_index_includes_seeds():
    import retrieval.hybrid as H

    H._INDEX = None
    chs = H._default_chunks()
    ids = {c.doc_id for c in chs}
    assert {"bnss_2023", "case_file_demo", "sc_bail_2022"} & ids, \
        "hybrid default index lacks seed docs"
    idx = H.get_index()
    hits = idx.retrieve(
        "FIR 0123/2024 status details", top_k=4, doc_ids=["case_file_demo"]
    )
    assert hits, "doc_ids-filtered seed query still refuses via get_index()"
    H._INDEX = None
