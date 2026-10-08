"""Generate 6-10 clearly-labelled SYNTHETIC bail case files -> data/raw/synthetic/.

Fictional persons, FIR numbers, dates, and courts. Every file starts with
"SYNTHETIC CASE FILE - FOR TESTING ONLY" and titles carry [SYNTHETIC].
Narratives state only fictional facts (who/when/where); no legal
exposition, so nothing can be mistaken for real law. Two fictional bail
matters (one granted-track, one rejected-track) across FIR, remand order,
charge-sheet excerpt, medical report, bail application, surety affidavit.

Re-run: .venv/bin/python corpus/make_case_files.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BANNER = "SYNTHETIC CASE FILE - FOR TESTING ONLY. All persons, FIR numbers, dates, and courts are fictional."

FILES: dict[str, str] = {
    "synth_cf_01_fir.txt": f"""{BANNER}

FIRST INFORMATION REPORT (synthetic)
FIR No. 0451/2024, Police Station Model Town (fictional), dated 12 March 2024.
Complainant: Ramesh Gupta (fictional) states that on 10 March 2024 a person
known to him as Vikas Sharma (fictional) took Rs. 2,50,000 promising to
arrange a shop allotment and thereafter stopped answering calls.
Offences invoked in the report: cheating and criminal breach of trust.
Accused named: Vikas Sharma, S/o Suresh Sharma, resident of 14 Rose Lane (all fictional).
""",
    "synth_cf_02_remand.txt": f"""{BANNER}

REMAMD PROCEEDINGS NOTE (synthetic; "remand" spelling as in fictional record)
Case: FIR No. 0451/2024 (fictional). Accused Vikas Sharma (fictional) was
produced before the Magistrate on 15 March 2024. The investigating officer
sought 5 days police custody stating that the money trail to two bank
accounts had to be verified. The Magistrate granted 3 days police custody
with directions that the accused be medically examined every 48 hours.
""",
    "synth_cf_03_chargesheet_excerpt.txt": f"""{BANNER}

CHARGE-SHEET EXCERPT (synthetic)
FIR No. 0451/2024 (fictional). The investigating officer records that bank
statements for March 2024 show a credit of Rs. 2,50,000 into the account of
Vikas Sharma (fictional) on 11 March 2024, and that the accused joined
investigation on 20 March 2024. The charge sheet lists 4 witnesses: the
complainant, two bank officials, and one neighbour. No recovery is pending
according to the investigating officer's note dated 28 March 2024.
""",
    "synth_cf_04_medical.txt": f"""{BANNER}

MEDICAL EXAMINATION REPORT (synthetic)
Accused: Vikas Sharma (fictional), examined at Civil Hospital (fictional) on
15 March 2024 and 18 March 2024. No fresh external injuries were recorded.
Blood pressure and pulse were within normal limits. The doctor declared the
accused fit for custody. Report signed by Dr. A. Nair (fictional), CMO.
""",
    "synth_cf_05_bail_application.txt": f"""{BANNER}

BAIL APPLICATION (synthetic, filed by the accused)
In FIR No. 0451/2024 (fictional), applicant Vikas Sharma (fictional) seeks
release on bail stating that he has cooperated with the investigation,
appeared on 20 March 2024 when summoned, has deep roots in the city, and
undertakes to attend every hearing and not to contact the complainant.
The application offers two local sureties and prays for lenient conditions.
""",
    "synth_cf_06_surety_affidavit.txt": f"""{BANNER}

SURETY AFFIDAVIT (synthetic)
Deponent: Mohan Lal (fictional), resident of 7 Lotus Street (fictional),
states on oath that he knows the applicant Vikas Sharma (fictional) for six
years, stands surety in the sum of Rs. 50,000, and undertakes to ensure the
applicant's presence at every hearing. Identity proof annexed: fictional
Aadhaar No. 9999-8888-7777 (invalid format, fictional).
""",
    "synth_cf_07_fir_second.txt": f"""{BANNER}

FIRST INFORMATION REPORT (synthetic, second matter)
FIR No. 0789/2024, Police Station Lake View (fictional), dated 02 June 2024.
Complainant: Sunita Rao (fictional) alleges that Ashok Verma (fictional)
criminally intimidated her on 30 May 2024 and has prior convictions in two
cheating cases of 2019 and 2021 (all fictional). The complainant states the
accused threatened her with dire consequences if she testified.
""",
    "synth_cf_08_bail_rejection_note.txt": f"""{BANNER}

COURT NOTE ON BAIL PLEA (synthetic, second matter)
FIR No. 0789/2024 (fictional). The prosecutor opposed bail for Ashok Verma
(fictional) citing the two prior convictions recorded in the charge sheet
and the allegation of witness intimidation dated 30 May 2024. The court
recorded that the investigation was at an early stage with statements of
three witnesses yet to be recorded, and deferred the bail plea by four
weeks. This note is fictional and creates no precedent.
""",
}


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    out = root / "data" / "raw" / "synthetic"
    out.mkdir(parents=True, exist_ok=True)
    for name, text in FILES.items():
        (out / name).write_text(text, encoding="utf-8")
    print(f"wrote {len(FILES)} synthetic case files to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
