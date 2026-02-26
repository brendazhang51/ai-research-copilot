You are Claude Code acting as a senior full-stack engineer.

Repository context:
- Project root: ./research-copilot
- FastAPI app lives in ./research-copilot/app
- Existing endpoints currently include: GET /health, POST /plan, POST /pubmed/search (PubMed integration already exists)
- OpenAI SDK: openai==2.21.0
- dotenv is used; .env exists at ./research-copilot/.env
- Uvicorn command used: python -m uvicorn app.main:app --reload --port 8000

Product intent:
- User wants a single "one-click" endpoint.
- User-facing output should be a readable report (Markdown), not raw JSON.
- Intermediate steps (PubMed query building, searching, summarizing) should be hidden from the user, but may be returned as debug fields.

Goal (Phase 2.5: Copilot Run Pipeline + Readable Report):
1) Add ONE primary user endpoint:
   - POST /copilot/run
   Request JSON:
     {
       "question": "string",
       "context": "string (optional)",
       "retmax": 6 (optional, 1-30),
       "include_debug": false (optional)
     }

   Response JSON must always include:
     {
       "report_markdown": "string"
     }

   If include_debug=true, include extra fields:
     - pubmed_queries (primary + fallback + extracted concepts)
     - articles (pmid/title/journal/year/abstract/citation)
     - literature_summaries (structured extraction per article)
     - analysis_plan (existing AnalysisPlan object)

2) Internally, /copilot/run must execute pipeline:
   a) Query Translator (LLM): natural-language question -> PubMed queries:
      - primary_query (more specific)
      - fallback_query (broader)
      - concepts dict: population/exposure/outcome keywords
      Return JSON via Pydantic schema.
   b) PubMed search:
      - use existing PubMed functions/module (do not break current /pubmed/search)
      - try primary_query; if results < 3 then try fallback_query
   c) Literature summarizer (LLM):
      - for each article abstract, extract: study_design, population, exposure, outcome, model, key_finding
      - if abstract missing, fill nulls and add notes
   d) Analysis plan generator (LLM):
      - reuse existing AnalysisPlan schema
      - incorporate literature summaries as context
   e) Report generator:
      - generate a readable Markdown report with sections:
        # Title (based on question)
        ## Research Question
        ## PubMed Search (show queries only briefly)
        ## Key Papers (bulleted citations)
        ## Evidence Summary (table-like bullets)
        ## Proposed Analysis Plan (human-readable bullets)
        ## Sensitivity Analyses
        ## Potential Biases & Limitations
      - Keep it concise but professional (SAP/protocol draft tone).
      - No raw JSON in the report body.

3) Keep existing endpoints unchanged: /health, /plan, /pubmed/search should still work.

4) Code organization:
   - Add/extend Pydantic models in app/schemas.py (or new file) for:
     CopilotRunRequest, CopilotRunResponse, QueryTranslation, PubMedArticle, LitSummary
   - Add LLM helper functions in app/planner.py (or new module):
     translate_to_pubmed_query(), summarize_literature(), generate_plan_with_lit(), generate_markdown_report()
   - Wire /copilot/run in app/main.py.

5) Dependency hygiene (important for deployment):
   - Ensure requirements.txt is deployable (no local path entries like "@ file://" or "/opt/miniconda3/conda-bld/...").
   - If such entries exist, replace them with normal pinned versions or remove if transitive.
   - Ensure required deps are included: fastapi, uvicorn, python-dotenv, openai, httpx, lxml.

6) Update README.md with:
   - Local run command
   - How to test /copilot/run in /docs
   - Example request payload
   - Note: include_debug optional

Constraints:
- Do NOT print or store OPENAI_API_KEY or any secrets.
- Do NOT add more user-facing endpoints besides /copilot/run.
- Ensure /copilot/run is robust and returns report_markdown even if literature is sparse (graceful degradation).
- Keep code clean and endpoints appear in Swagger docs.

After finishing, output:
- Summary of files changed/added
- Exact local commands to run
- Example JSON for /copilot/run

Extra UX: The response should also include a short "display_title" field extracted from the question (<= 80 chars) for future UI use.