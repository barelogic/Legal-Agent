"""Shared helpers for the draft/review/research workflows.

All three workflows render output ONLY from verified claims (plus user
input and fixed template boilerplate). This module holds the small
mechanics they share: keeping verified claims, renumbering claim_ids
globally (per-field pipelines each number from c1), and scoped retrieval.
"""

from contracts.schemas import Claim


def verified_only(claims: list[Claim]) -> list[Claim]:
    """Keep claims the verifier marked verified (defensive: refuse-by-default)."""
    return [c for c in claims if c.status == "verified"]


def renumber_claims(claims: list[Claim]) -> list[Claim]:
    """Reassign claim_ids c1..cN in order (per-field runs collide at c1)."""
    return [c.model_copy(update={"claim_id": f"c{i}"}) for i, c in enumerate(claims, 1)]
