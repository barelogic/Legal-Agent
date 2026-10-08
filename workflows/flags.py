"""Unified feature flags + shared run() entry for the API and eval harness.

Flags (I2: the four VERIFY_* stages plus relevance gates). All default ON;
each has a VERIFY_* env kill-switch (0/false/no/off disables):

  verify_text, entailment, citation_gate, regenerate  (verify stages)
  coverage, rerank, short_boost                        (relevance/retrieval)

Threshold *values* stay in env (MIN_COVERAGE, RERANK_MIN_SCORE); a flag
being off means that stage is skipped (coverage -> 0.0, rerank -> no
cutoff, boost -> no widening).

run(workflow, payload, flags=None, *, registry=None, llm=None) -> Answer
is the single pipeline entry: /answer calls it and the eval harness calls
it, so both use the same code path. payload carries question, top_k,
doc_ids, backend plus optional per-request flag overrides (I1: None means
inherit from flags/env — fully backward compatible). The active flags land
in Answer.trace["flags"].
"""

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, fields

logger = logging.getLogger(__name__)

FLAG_NAMES: tuple[str, ...] = (
    "verify_text",
    "entailment",
    "citation_gate",
    "regenerate",
    "coverage",
    "rerank",
    "short_boost",
)

_ENV_NAMES: dict[str, str] = {
    "verify_text": "VERIFY_TEXT",
    "entailment": "VERIFY_ENTAILMENT",
    "citation_gate": "VERIFY_CITATION_GATE",
    "regenerate": "VERIFY_REGENERATE",
    "coverage": "VERIFY_COVERAGE",
    "rerank": "VERIFY_RERANK",
    "short_boost": "VERIFY_SHORT_BOOST",
}

_OFF = {"0", "false", "no", "off", ""}


def _env_on(env_name: str, default: bool = True) -> bool:
    raw = os.getenv(env_name)
    if raw is None:
        return default
    return raw.strip().lower() not in _OFF


@dataclass(frozen=True)
class Flags:
    """All seven pipeline flags. Everything on unless switched off."""

    verify_text: bool = True
    entailment: bool = True
    citation_gate: bool = True
    regenerate: bool = True
    coverage: bool = True
    rerank: bool = True
    short_boost: bool = True

    @classmethod
    def from_env(cls) -> "Flags":
        """Read every flag from its VERIFY_* env var (default on)."""
        return cls(**{n: _env_on(_ENV_NAMES[n]) for n in FLAG_NAMES})

    def with_overrides(self, **kw) -> "Flags":
        """Copy with per-request overrides; None values inherit (I1)."""
        cur = {f.name: getattr(self, f.name) for f in fields(self)}
        for k, v in kw.items():
            if k in cur and v is not None:
                cur[k] = bool(v)
        return Flags(**cur)

    def as_dict(self) -> dict[str, bool]:
        """Active flags, for Answer.trace["flags"]."""
        return {n: getattr(self, n) for n in FLAG_NAMES}


def _get(payload, name: str, default=None):
    """Duck-typed read: works for AskIn models and eval-harness dicts."""
    if isinstance(payload, Mapping):
        return payload.get(name, default)
    return getattr(payload, name, default)


def flags_from_payload(payload, base: Flags | None = None) -> Flags:
    """Overlay per-request flag overrides (None = inherit) onto base."""
    base = base if base is not None else Flags.from_env()
    return base.with_overrides(
        **{n: _get(payload, n, None) for n in FLAG_NAMES}
    )


def run(workflow, payload, flags: Flags | None = None, *, registry=None, llm=None):
    """Shared pipeline entry: validate -> retrieve -> claims -> verify.

    Raises ValueError on bad input (the API layer translates to 422).
    Fallbacks (hybrid -> lexical) are recorded in trace and logged,
    never swallowed.
    """
    from generation.config import get_top_k
    from generation.llm import make_client
    from retrieval.hybrid import get_retrieval_backend
    from workflows.answer import answer_from_chunks, answer_question

    eff = flags_from_payload(payload, flags)
    question = _get(payload, "question", "") or ""
    if not question.strip():
        raise ValueError("question must not be empty")
    top_k = _get(payload, "top_k", None) or get_top_k()
    if not 1 <= top_k <= 50:
        raise ValueError("top_k must be 1..50")
    doc_ids = _get(payload, "doc_ids", None)
    backend = (_get(payload, "backend", None) or get_retrieval_backend()).strip().lower()

    if registry is None:
        from api.main import REGISTRY as _default_registry

        registry = _default_registry
    if llm is None:
        llm = make_client()

    # Flag off -> stage skipped (threshold neutralised, not removed).
    min_coverage = None if eff.coverage else 0.0
    rerank_min_score = None if eff.rerank else float("-inf")
    flagset = eff.as_dict()

    if backend == "hybrid" or doc_ids:
        from retrieval.hybrid import retrieve

        try:
            hits = retrieve(
                question, top_k=top_k, doc_ids=doc_ids,
                min_coverage=min_coverage, rerank_min_score=rerank_min_score,
            )
            ans = answer_from_chunks(
                question, workflow, registry, llm,
                [c for c, _ in hits], flagset=flagset,
            )
            ans.trace["backend"] = "hybrid"
            ans.trace["flags"] = flagset
            return ans
        except Exception as e:
            cause = f"hybrid failed ({e}); falling through to lexical"
            logger.warning("run fallthrough: %s", cause)
            ans = answer_question(
                question, workflow, registry, llm, top_k=top_k,
                min_coverage=min_coverage, short_boost=eff.short_boost,
                flagset=flagset,
            )
            ans.trace["backend"] = "lexical"
            ans.trace["fallback"] = cause
            ans.trace.setdefault("fallbacks", []).append(cause)
            ans.trace["flags"] = flagset
            return ans
    ans = answer_question(
        question, workflow, registry, llm, top_k=top_k,
        min_coverage=min_coverage, short_boost=eff.short_boost,
        flagset=flagset,
    )
    ans.trace["backend"] = "lexical"
    ans.trace["flags"] = flagset
    return ans
