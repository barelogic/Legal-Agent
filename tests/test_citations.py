"""Citation gate: only registry-backed cites survive."""

from contracts.schemas import Chunk, Citation, Claim, Doc
from verify.citations import (
    build_citations,
    extract_citation_mentions,
    gate_citations,
    gate_claim_citations,
    resolve_raw,
)


def _setup():
    docs = {"bnss_2023": Doc(doc_id="bnss_2023", title="BNSS", doc_type="statute", citation="BNSS, 2023")}
    cmap = {"bnss_2023::p1::c0": Chunk(chunk_id="bnss_2023::p1::c0", doc_id="bnss_2023", text="bail text")}
    claims = [Claim(claim_id="c1", text="t", chunk_ids=["bnss_2023::p1::c0"], quote="bail text")]
    return docs, cmap, claims


def test_build_resolved_only():
    docs, cmap, claims = _setup()
    cites = build_citations(claims, cmap, docs)
    assert len(cites) == 1 and cites[0].resolved and cites[0].doc_id == "bnss_2023"


def test_gate_drops_hallucinated():
    docs, _, _ = _setup()
    raw = [
        Citation(cite_id="x", raw="BNSS, 2023"),
        Citation(cite_id="y", raw="Some Imaginary Case AIR 2099 SC 1"),
    ]
    kept = gate_citations(raw, docs)
    assert len(kept) == 1 and kept[0].doc_id == "bnss_2023"


def test_doc_id_substring_needs_word_boundary():
    docs, _, _ = _setup()
    assert resolve_raw("see bnss_2023 supra", docs) is not None
    assert resolve_raw("xbnss_2023y", docs) is None
    assert resolve_raw("mybnss_20230", docs) is None


def test_extract_mentions():
    text = (
        "Under Section 483 of the Bharatiya Nagarik Suraksha Sanhita, "
        "Satender Kumar Antil v. CBI holds bail is the rule, see (2022) 10 SCC 123."
    )
    mentions = extract_citation_mentions(text)
    assert any("Section 483 of" in m for m in mentions)
    assert any("Antil v. CBI" in m for m in mentions)
    assert any("SCC" in m for m in mentions)
    # Bare "Section N" is a number check, not a citation mention.
    assert extract_citation_mentions("Relief under Section 483.") == []


def test_gate_claim_unresolved_case_fails():
    docs, cmap, _ = _setup()
    chunk = next(iter(cmap.values()))
    reason = gate_claim_citations(
        "In Sharma v. State of Utopia (2024), bail is the rule.",
        "bail text",
        [chunk],
        docs,
    )
    assert reason is not None and "Sharma" in reason
