"""Citation gate: only registry-backed cites survive."""

from contracts.schemas import Chunk, Citation, Claim, Doc
from verify.citations import build_citations, gate_citations


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
