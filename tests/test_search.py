"""CLI: --min-overlap reaches retrieve()."""

import retrieval.search as s


def test_min_overlap_passthrough(monkeypatch):
    seen = {}

    def _fake(query, top_k=8, doc_ids=None, min_overlap=2):
        seen.update(query=query, top_k=top_k, doc_ids=doc_ids, min_overlap=min_overlap)
        return []

    monkeypatch.setattr(s, "retrieve", _fake)
    assert s.main(["bail?", "--min-overlap", "1"]) == 0
    assert seen["min_overlap"] == 1
