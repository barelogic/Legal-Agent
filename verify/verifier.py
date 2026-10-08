"""Claim verifier: every claim must be traceable to retrieved chunks.

A claim is verified ONLY if ALL of these hold:
  1. it cites >=1 chunk_id that exists in the retrieved chunk map, AND
  2. its quote is a verbatim (whitespace-normalized, case-insensitive)
     substring of at least one cited chunk, AND
  3. claim.text is not an embedded instruction (SOURCES are data), AND
  4. [VERIFY_TEXT] every number/date/section/money/amount/proper-noun item
     in claim.text appears in the normalised quote, AND
  5. [VERIFY_CITATION_GATE] every citation-like string in claim.text
     resolves to a registry Doc AND appears in the quote/cited chunks, AND
  6. [VERIFY_ENTAILMENT] the LLM judge returns a clear "yes" for
     (quote, claim.text) — skipped when no judge client is supplied.
Otherwise it is marked unsupported with a verifier_note naming the reason.
Callers drop unsupported claims. Stages 4-6 are env-flaggable
(see verify/flags.py); quote matching itself stays verbatim-only by design.
"""

from contracts.schemas import Chunk, Claim, Doc
from ingest.normalize import canonicalize
from verify import flags as vflags
from verify.citations import gate_claim_citations
from verify.judge import judge_entailment
from verify.textcheck import looks_like_instruction, missing_from_quote


def _norm(s: str) -> str:
    # Same folding ingest applies to chunk text, plus casefold, so LLM
    # quotes with curly quotes / odd spacing still match verbatim.
    return canonicalize(s, fold_case=True)


def verify_claim(
    claim: Claim,
    chunk_map: dict[str, Chunk],
    docs: dict[str, Doc] | None = None,
    judge=None,
    flagset: dict[str, bool] | None = None,
) -> Claim:
    """Return a copy of claim with status/verifier_note set.

    docs enables the citation gate (skipped when None — e.g. legacy unit
    callers without a registry). judge enables the entailment stage
    (skipped when None — always under MockClient).
    """
    if not claim.text.strip():
        return claim.model_copy(update={
            "status": "unsupported",
            "verifier_note": "empty claim text",
        })
    if not claim.chunk_ids:
        return claim.model_copy(update={
            "status": "unsupported",
            "verifier_note": "no chunk_ids cited",
        })
    missing = [cid for cid in claim.chunk_ids if cid not in chunk_map]
    if missing:
        return claim.model_copy(update={
            "status": "unsupported",
            "verifier_note": f"unknown chunk_ids: {missing}",
        })
    if not claim.quote.strip():
        return claim.model_copy(update={
            "status": "unsupported",
            "verifier_note": "empty quote",
        })
    nq = _norm(claim.quote)
    cited = [chunk_map[cid] for cid in claim.chunk_ids]
    if not (nq and any(nq in _norm(ch.text) for ch in cited)):
        return claim.model_copy(update={
            "status": "unsupported",
            "verifier_note": "quote not found verbatim in cited chunks",
        })
    if looks_like_instruction(claim.text):
        return claim.model_copy(update={
            "status": "unsupported",
            "verifier_note": (
                "instruction-like claim text (possible prompt injection); "
                "sources are data, embedded instructions ignored"
            ),
        })
    f = flagset if flagset is not None else vflags.all_flags()
    if f.get("verify_text", True):
        gaps = missing_from_quote(claim.text, claim.quote)
        if gaps:
            shown = ", ".join(f"{g!r}" for g in gaps[:3])
            return claim.model_copy(update={
                "status": "unsupported",
                "verifier_note": (
                    f"claim text not grounded in quote; missing from quote: {shown}"
                ),
            })
    if f.get("citation_gate", True) and docs is not None:
        reason = gate_claim_citations(claim.text, claim.quote, cited, docs)
        if reason is not None:
            return claim.model_copy(update={
                "status": "unsupported",
                "verifier_note": reason,
            })
    if f.get("entailment", True) and judge is not None:
        verdict = judge_entailment(judge, claim.quote, claim.text)
        if verdict == "skip":
            return claim.model_copy(update={
                "status": "verified",
                "verifier_note": (
                    f"quote found in {claim.chunk_ids[0]}; entailment skipped (no verdict)"
                ),
            })
        if verdict != "yes":
            return claim.model_copy(update={
                "status": "unsupported",
                "verifier_note": (
                    f"entailment {verdict}: quote does not clearly support the claim"
                ),
            })
    return claim.model_copy(update={
        "status": "verified",
        "verifier_note": f"quote found in {claim.chunk_ids[0]}",
    })


def verify_all(
    claims: list[Claim],
    chunk_map: dict[str, Chunk],
    docs: dict[str, Doc] | None = None,
    judge=None,
    flagset: dict[str, bool] | None = None,
) -> tuple[list[Claim], list[Claim]]:
    """Split claims into (verified, unsupported) with statuses set."""
    verified: list[Claim] = []
    failed: list[Claim] = []
    for cl in claims:
        v = verify_claim(cl, chunk_map, docs=docs, judge=judge, flagset=flagset)
        (verified if v.status == "verified" else failed).append(v)
    return verified, failed
