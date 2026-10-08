"""Templates: valid JSON, required shape, no invented section numbers."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMPL = ROOT / "templates"

SECTION_NO = re.compile(r"section\s+\d+", re.I)


def _load(name: str) -> dict:
    return json.loads((TMPL / name).read_text(encoding="utf-8"))


def test_all_templates_present_and_shaped():
    for name in ("bail_application.json", "legal_notice.json", "affidavit.json"):
        t = _load(name)
        assert t["template_id"] and t["boilerplate_structure"]
        assert isinstance(t["required_fields"], list) and t["required_fields"]
        for f in t["required_fields"]:
            for k in ("name", "field_type", "required", "typically_found_in", "description"):
                assert k in f, f"{name}:{f}"
        orders = [s["order"] for s in t["boilerplate_structure"]]
        assert orders == sorted(orders)


def test_no_invented_section_numbers():
    blob = "\n".join((TMPL / n).read_text(encoding="utf-8") for n in (
        "bail_application.json", "legal_notice.json", "affidavit.json"))
    assert not SECTION_NO.search(blob), "templates must not hardcode statutory section numbers"


def test_no_baked_clocks_or_identifiers():
    """Periods and provision identifiers stay fill-in fields, not template text."""
    blob = "\n".join((TMPL / n).read_text(encoding="utf-8") for n in (
        "bail_application.json", "legal_notice.json", "affidavit.json"))
    assert not re.search(r"\b\d+\s*(days?|months?|years?|hours?)\b", blob), \
        "templates must not bake statutory clocks (fill from sources)"
    assert "Order XIX" not in blob, "procedural provisions are fill-in, not pre-filled"


def test_sources_doc_exists():
    doc = ROOT / "docs" / "templates_sources.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    assert "http" in text
