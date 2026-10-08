# Legal Agent: Grounded & Verifiable

## Architecture and Guarantees
Judges care about verifiability. Our system ensures every fact visibly links to its source, and it remains honest about what is missing and what protection was active.

**Core Wording & Guarantee:** Every sentence is a claim whose key facts and quote are checked against the source, with the quote shown beside it.

**User-Provided vs. Sourced Facts:** User-provided values stay visually distinct from sourced facts with dedicated amber `[USER-PROVIDED]` chips. We never hide a refusal, a missing-info item, a contradiction, or a fallback. 

## Evaluation & Metrics
The measure of the verifier is `baseline_no_verify` (6 to 0); plain RAG vs ours also changes retrieval. 

Fabrication metrics depend on the mode. For example, cite fabrication numbers specific to the combination of generator, retrieval, and judge mode (as seen in our Compare view).

---

# 4-Minute Demo Script

**Setup**
1. Ensure the backend is running (`python -m uvicorn api.main:app`).
2. Run the UI (`streamlit run ui/app.py`).

**Step 1: Chat & Research (0:00 - 1:00)**
- Open the **💬 Chat** tab.
- Click **Fill example** ("bail in non-bailable offences?") and hit **Ask**.
- Point out the response: "Every sentence is a claim whose key facts and quote are checked against the source, with the quote shown beside it."
- Click on one of the `[cN]` chips to open the source evidence overlay. Show the verbatim quote perfectly matching the chunk.
- Note the **Trace (debug)** and **Fallbacks/Protections** banners.

**Step 2: Draft Precheck (1:00 - 2:00)**
- Switch to the **📝 Draft** tab. 
- Select a template (e.g., `bail_application`).
- Click **Run precheck**. 
- Highlight the **Draft Readiness** progress bar. The system honestly degrades, listing exactly which required fields are missing and why they are needed.

**Step 3: Redraft with Values (2:00 - 3:00)**
- In the "Missing information" inputs, type values (e.g., FIR number: "0123/2024").
- Click **Re-draft with provided values**.
- Show the generated draft. Emphasize that the user's typed values appear as amber `[USER-PROVIDED: ...]` chips, clearly separated from verified green sourced facts.

**Step 4: Compare View (3:00 - 4:00)**
- Switch to the **📊 Compare** tab.
- Select a query to compare our grounded pipeline against the baseline.
- Explain: "The measure of the verifier is baseline_no_verify (6 to 0); plain RAG vs ours also changes retrieval."
- Show how the baseline hallucinates or fails to verify claims, whereas our system successfully drops unverified claims and remains grounded.

**Offline Fallback (Backup plan)**
- If the network fails, flip **Use fixtures** in the sidebar. All tabs instantly load valid local mock data (demonstrating resilience).
