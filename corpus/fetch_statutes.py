"""Fetch statutes: MHA bare-Act PDFs + India Code bail sections.

- New acts (BNS/BSA/BNSS): official MHA PDFs -> data/raw/statutes/.
- Bail provisions + anchoring sections of BNSS/CrPC/IPC/Evidence Act:
  discovered via the India Code DSpace API (never from memory: section
  numbers/titles/text come from API metadata) -> data/raw/india_code/.
- Writes data/raw/_fetch_log.json (url, path, sha256, bytes, accessed).

Re-run: .venv/bin/python corpus/fetch_statutes.py
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from corpus.sources import SOURCES

UA = {"User-Agent": "Mozilla/5.0 (research; hackathon eval corpus builder)"}
IC_API = "https://indiacode.gov.in/server/api"

MHA_PDFS = [s for s in SOURCES if s["kind"] == "statute_pdf"]

# Discovery queries: (act name filter, keyword). Section numbers are taken
# from returned metadata, never hardcoded here.
SECTION_DISCOVERY: list[tuple[str, str, int]] = [
    ("Bharatiya Nagarik Suraksha Sanhita", "bail", 12),
    ("Bharatiya Nagarik Suraksha Sanhita", "bond or bail bond", 6),
    ("Bharatiya Nagarik Suraksha Sanhita", "undertrial prisoner detained", 3),
    ("Bharatiya Nagarik Suraksha Sanhita", "When bail may be taken in case of non-bailable offence", 4),
    ("Bharatiya Nagarik Suraksha Sanhita", "anticipatory bail", 6),
    ("Code of Criminal Procedure", "bail", 12),
    ("Code of Criminal Procedure", "short title commencement", 2),
    ("Indian Penal Code", "short title commencement extent", 2),
    ("Indian Evidence Act", "short title extent commencement", 2),
    ("Bharatiya Nyaya Sanhita", "short title commencement", 2),
    ("Bharatiya Sakshya Adhiniyam", "short title application commencement", 2),
]


def _slug(s: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return slug or "sec"


def strip_html(h: str) -> str:
    """Section page-note HTML -> plain text (entities unescaped, ws collapsed)."""
    t = re.sub(r"<[^>]+>", " ", h or "")
    return " ".join(html.unescape(t).split())


def fetch_pdf(url: str, dest: Path, timeout: int = 120) -> dict:
    """Download url to dest. Returns log entry (raises on HTTP error)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return {
        "url": url,
        "path": str(dest),
        "sha256": hashlib.sha256(r.content).hexdigest(),
        "bytes": len(r.content),
        "accessed": date.today().isoformat(),
    }


def discover_sections(act_filter: str, keyword: str, size: int = 12) -> list[dict]:
    """Query India Code; return items whose act name matches act_filter."""
    r = requests.get(
        f"{IC_API}/discover/search/objects",
        params={"query": f"{act_filter} {keyword}", "size": size},
        headers=UA,
        timeout=30,
    )
    r.raise_for_status()
    out: list[dict] = []
    objs = r.json()["_embedded"]["searchResult"]["_embedded"]["objects"]
    for o in objs:
        io = o["_embedded"]["indexableObject"]
        it = requests.get(f"{IC_API}/core/items/{io['uuid']}?projection=full",
                           headers=UA, timeout=30).json()
        md = it.get("metadata", {})
        act = " ".join(x["value"] for x in md.get("dc.identifier.act_name", []))
        if act_filter.lower() not in act.lower():
            continue
        sec = " ".join(x["value"] for x in md.get("dc.identifier.section_number", []))
        title = " ".join(x["value"] for x in md.get("dc.title", []))
        note = " ".join(x["value"] for x in md.get("dc.identifier.section_page_note", []))
        handle = io.get("handle", "")
        if not (sec and note.strip()):
            continue
        out.append({
            "act_name": act,
            "section_number": sec.strip(),
            "title": title.strip(),
            "text": strip_html(note),
            "handle": handle,
            "source_url": f"https://indiacode.gov.in/handle/{handle}" if handle else "",
            "uuid": io["uuid"],
        })
    return out


def save_section(sec: dict, dest_dir: Path) -> Path:
    """Write one section .txt with provenance header. Returns path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{_slug(sec['act_name'])[:40]}_s{sec['section_number']}_{sec['uuid'][:8]}.txt"
    p = dest_dir / fname
    header = (
        f"Source: {sec['source_url']}\n"
        f"Act: {sec['act_name']}\n"
        f"Section: {sec['section_number']}\n"
        f"Title: {sec['title']}\n"
        f"(Text below is the India Code section_page_note for this section.)\n\n"
    )
    p.write_text(header + sec["text"] + "\n", encoding="utf-8")
    return p


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    raw = root / "data" / "raw"
    log: list[dict] = []
    # 1) MHA PDFs
    pdf_dir = raw / "statutes"
    for s in MHA_PDFS:
        dest = pdf_dir / f"{_slug(s['title'])}.pdf"
        try:
            entry = fetch_pdf(s["url"], dest)
            entry["title"] = s["title"]
            log.append(entry)
            print(f"pdf ok: {dest.name} ({entry['bytes']} bytes)")
        except Exception as e:
            print(f"pdf FAIL {s['url']}: {e}")
    # 2) India Code sections
    sec_dir = raw / "india_code"
    seen: set[str] = set()
    n_sec = 0
    for act_filter, keyword, size in SECTION_DISCOVERY:
        try:
            secs = discover_sections(act_filter, keyword, size=size)
        except Exception as e:
            print(f"discover FAIL {act_filter} / {keyword}: {e}")
            continue
        for sec in secs:
            key = (sec["act_name"], sec["section_number"])
            if key in seen:
                continue
            seen.add(key)
            p = save_section(sec, sec_dir)
            log.append({"url": sec["source_url"], "path": str(p),
                        "title": f"{sec['act_name']} s.{sec['section_number']}",
                        "accessed": date.today().isoformat()})
            n_sec += 1
            print(f"section ok: {sec['act_name'][:40]} s.{sec['section_number']}")
    (raw / "_fetch_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(f"done: {len(MHA_PDFS)} pdf attempts, {n_sec} sections saved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
