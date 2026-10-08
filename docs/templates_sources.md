# Template sources (public)

Structures below inform `templates/*.json`. No statutory section numbers
are baked into the templates — provisions stay fill-in fields sourced from
retrieved documents at answer time.

## Bail application

- Delhi High Court cause-list / practice directions circulated 26.05.2026
  (via delhihighcourt.nic.in combined cause-list PDF, item 13.05.2026):
  mandatory bail-affidavit disclosure heads — (A) case details (FIR number
  & date, police station/district/state, sections, maximum punishment);
  (B) custody & procedural compliance (arrest date, custody undergone);
  (C) trial status (stage, witnesses cited/examined); (D) criminal
  antecedents (FIR, PS, sections, status); (E) previous bail applications
  (court, case no., outcome); (F) coercive processes (NBW, proclaimed
  offender). Used for `required_fields` + `antecedents_and_history`.
- Delhi High Court bail orders (BAIL APPLN. 376/2026, 890/2026; BAIL
  APPLN. 3562/2025; Allahabad anticipatory-bail order NABAIL 472/2026;
  Sikkim Bail Application No. 03/2026): cause-title shape, FIR/PS/case
  framing, custody-length and parity grounds, personal-bond + surety
  prayer. Used for `cause_title`, `facts`, `grounds`, `prayer`.
- JuriGram, "Bail Application Format — Sessions Court"
  (https://jurigram.com/advocates/resources/legal-drafting/bail-application-format-sessions-court):
  regular-bail drafting guide; structure reference only.

## Legal notice

- iPleaders, "How to send a legal notice in India: 2026 format, process
  and templates" (https://blog.ipleaders.in/legal-notice-2, verified
  25.06.2026): 8-component anatomy (date/letterhead, parties, subject,
  facts, legal grounds, demand, compliance period, signature + retained
  copy); Section 80 CPC 2-month rule and Section 138 NI 30-day notice /
  15-day pay / 30-day complaint clocks; RPAD + email/WhatsApp service
  practice. Used for `boilerplate_structure`, `conditional_fields`,
  `notes`.
- Section 80 CPC requisites note (Uttarkashi judiciary PDF via
  cdnbbsr.s3waas.gov.in): plaintiff particulars, cause of action and
  relief with sufficient particularity, written delivery to the proper
  office, suit after 2 months with plaint statement. Used for the
  `s80_authority` conditional.
- Delhi High Court Practice Direction 157 (Nov 2025, Section 138 NI
  complaints): synopsis fields — parties, cheque details, dishonour
  memo, statutory notice (date/mode/tracking/delivery), cause of action,
  relief. Used for the `s138_*` conditional fields.
- Legal Service India, "Legal Notice in India" (legalserviceindia.com):
  sender/addressee/facts/grievance/grounds/demand/time-limit/warning/
  signature structure; notice types (recovery, 138, s.80 CPC,
  employment). Cross-check for `required_fields`.

## Affidavit

- CPC Order XIX Rule 3 (https://indiacode.ecourtsindia.com/cpc/order/xix/rule/3):
  confine to personal-knowledge facts except on interlocutory
  applications; state source for information/belief. Used for
  `knowledge_source_per_para` + formatting rules.
- CPC Order XIX Rule 6 (https://indiacode.ecourtsindia.com/cpc/order/xix/rule/6):
  chronological sequence; no mere reproduction of pleadings/legal
  grounds; one subject portion per paragraph; knowledge-vs-belief
  statement with sources; consecutive pagination, numbered paragraphs,
  figures for numbers/dates, annexure + page references. Used for
  `boilerplate_structure` + `formatting_rules`.
- PleadEasy, "Affidavit Format for Court (2026)"
  (https://www.pleadeasy.in/formats/affidavit): filing-order parts —
  cause title, deponent identification, numbered averments, source of
  knowledge, prayer/purpose, verification (para-wise knowledge vs
  belief), attestation u/s 139 CPC; common defects list. Used for
  section order + `notes`.
- LiveLaw columns on affidavits / Order 19 vs Supreme Court Rules
  Order 11 (livelaw.in): affirmation before competent authority,
  cross-examination power, verification genuineness. Background only.
