"""Env flags for verifier hardening. All default ON; set to 0/false/no/off to disable.

Flags are read at call time (not import time) so tests can toggle via monkeypatch.
"""

import os

_OFF = {"0", "false", "no", "off", ""}


def _on(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in _OFF


def verify_text_enabled() -> bool:
    """Deterministic claim-text-vs-quote item check."""
    return _on("VERIFY_TEXT", True)


def entailment_enabled() -> bool:
    """LLM entailment judge (auto-skipped under MockClient)."""
    return _on("VERIFY_ENTAILMENT", True)


def citation_gate_enabled() -> bool:
    """Citation-like strings in claim.text must resolve + appear in sources."""
    return _on("VERIFY_CITATION_GATE", True)


def regenerate_enabled() -> bool:
    """One retry with failure notes when >30% of claims fail."""
    return _on("VERIFY_REGENERATE", True)


def all_flags() -> dict[str, bool]:
    """Snapshot for Answer.trace.verify_flags."""
    return {
        "verify_text": verify_text_enabled(),
        "entailment": entailment_enabled(),
        "citation_gate": citation_gate_enabled(),
        "regenerate": regenerate_enabled(),
    }
