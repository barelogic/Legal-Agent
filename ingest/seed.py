"""Load seed .txt files from data/ into Doc + Chunk objects."""

from pathlib import Path

from contracts.schemas import Doc
from ingest.chunker import chunk_text
from retrieval.store import Registry

# doc_id -> (title, doc_type, citation, section_label)
SEED_META: dict[str, tuple[str, str, str | None, str | None]] = {
    "bnss_2023": (
        "Bharatiya Nagarik Suraksha Sanhita, 2023 (excerpt)",
        "statute",
        "BNSS, 2023",
        "Section 483",
    ),
    "sc_bail_2022": (
        "Supreme Court bail principles (demo excerpt)",
        "judgment",
        "Satender Kumar Antil v. CBI (2022)",
        "Para 14",
    ),
    "case_file_demo": (
        "Demo case file FIR No. 0123/2024",
        "case_file",
        None,
        "FIR summary",
    ),
}


def load_seeds(data_dir: Path | str = "data") -> Registry:
    """Read data/*.txt, register Docs, chunk and store. Missing dir -> empty registry."""
    reg = Registry()
    base = Path(data_dir)
    if not base.is_dir():
        return reg
    for txt_path in sorted(base.glob("*.txt")):
        doc_id = txt_path.stem
        title, doc_type, citation, section = SEED_META.get(
            doc_id, (txt_path.stem, "case_file", None, None)
        )
        doc = Doc(
            doc_id=doc_id,
            title=title,
            doc_type=doc_type,  # type: ignore[arg-type]
            citation=citation,
        )
        reg.register_doc(doc)
        text = txt_path.read_text(encoding="utf-8")
        reg.add_chunks(chunk_text(doc, text, section_label=section))
    return reg
