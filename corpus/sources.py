"""Source registry: every corpus source with URL + licence/terms note.

Machine-readable so fetch scripts and corpus/README.md cannot drift.
Statute section numbers are NOT stored here (they come from India Code
metadata at fetch time); only source endpoints and licences live here.
"""

SOURCES: list[dict] = [
    {
        "key": "mha_bns_pdf",
        "kind": "statute_pdf",
        "title": "The Bharatiya Nyaya Sanhita, 2023",
        "url": "https://www.mha.gov.in/sites/default/files/2024-04/250883_english_01042024.pdf",
        "via": "MHA New Criminal Laws page (https://www.mha.gov.in/en/commoncontent/new-criminal-laws)",
        "licence": "Government of India work; free to access/download from mha.gov.in",
        "terms_note": "Official bare Act PDF as hosted by MHA. Reproduce verbatim; no modification.",
    },
    {
        "key": "mha_bsa_pdf",
        "kind": "statute_pdf",
        "title": "The Bharatiya Sakshya Adhiniyam, 2023",
        "url": "https://www.mha.gov.in/sites/default/files/2024-04/250882_english_01042024_0.pdf",
        "via": "MHA New Criminal Laws page",
        "licence": "Government of India work; free to access/download from mha.gov.in",
        "terms_note": "Official bare Act PDF as hosted by MHA. Reproduce verbatim; no modification.",
    },
    {
        "key": "mha_bnss_pdf",
        "kind": "statute_pdf",
        "title": "The Bharatiya Nagarik Suraksha Sanhita, 2023",
        "url": "https://www.mha.gov.in/sites/default/files/2024-04/250884_2_english_01042024.pdf",
        "via": "MHA New Criminal Laws page",
        "licence": "Government of India work; free to access/download from mha.gov.in",
        "terms_note": "Official bare Act PDF as hosted by MHA. Reproduce verbatim; no modification.",
    },
    {
        "key": "indiacode_api",
        "kind": "statute_sections_api",
        "title": "India Code DSpace API (section-level authoritative text)",
        "url": "https://indiacode.gov.in/server/api",
        "via": "indiacode.gov.in (migrated from indiacode.nic.in)",
        "licence": "Government of India statute text; API openly queryable, no key",
        "terms_note": "Section text taken from dc.identifier.section_page_note metadata; "
        "source_url per section = https://indiacode.gov.in/handle/<handle>. "
        "Used for bail provisions of BNSS/CrPC and anchoring sections of IPC/CrPC/Evidence Act.",
    },
    {
        "key": "hf_indian_case_laws",
        "kind": "judgments",
        "title": "Sumitedu/indian-case-laws (KanoonGPT Open Legal Data Initiative)",
        "url": "https://huggingface.co/datasets/Sumitedu/indian-case-laws",
        "via": "HuggingFace datasets, streaming",
        "licence": "apache-2.0 (dataset card)",
        "terms_note": "Judgment metadata summaries + headnotes; source_pdf_s3_url per row "
        "points at the underlying court PDF mirror. indexable_text is a summary, "
        "not the full judgment: chunks support case-level facts only.",
    },
    {
        "key": "synthetic_case_files",
        "kind": "case_files",
        "title": "Synthetic bail case files (generated for this corpus)",
        "url": "",
        "via": "corpus/make_case_files.py",
        "licence": "created for this hackathon; fictional persons/events",
        "terms_note": "SYNTHETIC and clearly labelled in title + first line. "
        "Purely fictional narratives; no real persons, FIR numbers, or courts. "
        "Must never be cited as real law or real cases.",
    },
]

# Official comparison-table sources attempted for corpus/section_map.json.
COMPARISON_SOURCES_ATTEMPTED: list[dict] = [
    {
        "source": "BPR&D comparative charts (bprd.nic.in)",
        "url": "https://bprd.nic.in/",
        "result": "unreachable from this environment (https timeout; http 302 then timeout)",
    },
    {
        "source": "MHA New Criminal Laws page tables",
        "url": "https://www.mha.gov.in/en/commoncontent/new-criminal-laws",
        "result": "reachable; hosts only the 3 bare-Act PDFs, no correspondence table",
    },
    {
        "source": "NCRB Sankalan portal",
        "url": "https://ncrb.gov.in/uploads/SankalanPortal/Index.html",
        "result": "reachable; hosts Act/Gazette PDFs, no correspondence table found",
    },
    {
        "source": "eGazette",
        "url": "https://egazette.nic.in/",
        "result": "unreachable (timeout)",
    },
    {
        "source": "Supreme Court portal / eSCR",
        "url": "https://supremecourt.gov.in/",
        "result": "unreachable (timeout)",
    },
]
