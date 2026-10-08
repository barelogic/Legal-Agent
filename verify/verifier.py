"""Claim verifier: every claim must be traceable to retrieved chunks.

A claim is verified ONLY if:
  1. it cites >=1 chunk_id that exists in the retrieved chunk map, AND
  2. its quote is a verbatim (whitespace-normalized, case-insensitive)
     substring of at least one cited chunk.
Otherwise it is marked unsupported. Callers drop unsupported claims.
"""

from contracts.schemas import Chunk, Claim
from ingest.normalize import canonicalize


def _norm(s: str) -> str:
    # Same folding ingest applies to chunk text, plus casefold, so LLM
    # quotes with curly quotes / odd spacing still match verbatim.
    return canonicalize(s, fold_case=True)


def verify_claim(claim: Claim, chunk_map: dict[str, Chunk]) -> Claim:
    """Return a copy of claim with status/verifier_note set."""
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
    for cid in claim.chunk_ids:
        if nq and nq in _norm(chunk_map[cid].text):
            return claim.model_copy(update={
                "status": "verified",
                "verifier_note": f"quote found in {cid}",
            })
    return claim.model_copy(update={
        "status": "unsupported",
        "verifier_note": "quote not found verbatim in cited chunks",
    })


def verify_all(
    claims: list[Claim], chunk_map: dict[str, Chunk]
) -> tuple[list[Claim], list[Claim]]:
    """Split claims into (verified, unsupported) with statuses set."""
    verified: list[Claim] = []
    failed: list[Claim] = []
    for cl in claims:
        v = verify_claim(cl, chunk_map)
        (verified if v.status == "verified" else failed).append(v)
    return verified, failed
