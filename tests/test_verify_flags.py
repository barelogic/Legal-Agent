"""Verify flags: all ON by default, individually switchable."""

from verify import flags as vflags


def test_defaults_on(monkeypatch):
    for k in ("VERIFY_TEXT", "VERIFY_ENTAILMENT", "VERIFY_CITATION_GATE", "VERIFY_REGENERATE"):
        monkeypatch.delenv(k, raising=False)
    assert vflags.all_flags() == {
        "verify_text": True,
        "entailment": True,
        "citation_gate": True,
        "regenerate": True,
    }


def test_individual_off(monkeypatch):
    monkeypatch.setenv("VERIFY_TEXT", "0")
    monkeypatch.setenv("VERIFY_ENTAILMENT", "off")
    assert not vflags.verify_text_enabled()
    assert not vflags.entailment_enabled()
    assert vflags.citation_gate_enabled()
    assert vflags.regenerate_enabled()
