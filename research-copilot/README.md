# AI Research Copilot

A FastAPI service that generates structured epidemiological analysis plans, searches PubMed for relevant literature (with LLM-based re-ranking for relevance), and compiles everything into a readable Markdown report.

## Setup

```bash
cd research-copilot
pip install -r requirements.txt
```

Create a `.env` file with your OpenAI key:

```
OPENAI_API_KEY=sk-...
```

## Start the server

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Interactive API docs: <http://localhost:8000/docs>

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/copilot/run` | **One-click pipeline** — query translation → PubMed (over-fetch) → LLM re-rank → summarisation → causal plan → Markdown report |
| POST | `/plan` | Generate a structured analysis plan only |
| POST | `/pubmed/search` | Search PubMed and return article metadata |
| POST | `/plan_with_literature` | Generate plan + fetch PubMed literature in parallel |

---

## Primary endpoint: POST /copilot/run

### Pipeline overview (v0.2)

```
question
  └─ A) LLM query translation (MeSH-enriched PubMed queries)
       └─ B) PubMed search — fetches retmax_candidates = min(max(retmax×4, 20), 40)
            └─ B2) LLM re-ranker — scores candidates, selects top retmax by relevance
                 └─ C) Per-article summarisation (parallelised LLM)
                      └─ D) Causal analysis plan (enforces confounder ≠ predictor)
                           └─ E) Markdown report
```

### Request

```json
{
  "question": "Does statin use reduce all-cause mortality in elderly patients with type 2 diabetes?",
  "context": "Retrospective cohort using EHR data, adults aged 65+",
  "retmax": 6,
  "include_debug": false
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `question` | string | required | Research question (≥ 5 chars) |
| `context` | string | null | Optional background / dataset description |
| `retmax` | int 1–30 | `6` | Articles shown to user (pipeline fetches up to 4× more as candidates) |
| `include_debug` | bool | `false` | Include intermediate pipeline outputs including `rerank_debug` |

### Response (always returned)

```json
{
  "report_markdown": "# Does statin use reduce...\n## Research Question\n...",
  "display_title": "Does statin use reduce all-cause mortality in elderly..."
}
```

### Response with `include_debug: true` (additional fields)

```json
{
  "report_markdown": "...",
  "display_title": "...",
  "pubmed_queries": {
    "primary_query": "statins[MeSH] AND mortality AND (diabetes mellitus, type 2[MeSH]) AND aged[MeSH]",
    "fallback_query": "statin mortality type 2 diabetes elderly",
    "concepts": { "population": "elderly diabetes", "exposure": "statins", "outcome": "all-cause mortality" }
  },
  "articles": [
    { "pmid": "...", "title": "...", "journal": "...", "year": "...", "abstract": "...", "citation": "..." }
  ],
  "literature_summaries": [
    {
      "pmid": "...", "study_design": "cohort", "key_finding": "...",
      "adjustment_set": "age, sex, diabetes duration, baseline HbA1c, eGFR"
    }
  ],
  "analysis_plan": {
    "population": "...", "exposure": "...", "outcome": "...",
    "time_zero_definition": "...", "exposure_window": "...", "outcome_window": "...",
    "exposure_modeling": ["Continuous with 3-knot RCS at 10th/50th/90th percentiles", "Quartile categories"],
    "key_confounders": ["age", "sex", "diabetes duration", "baseline cardiovascular disease", "..."],
    "sensitivity_analyses": ["..."], "potential_biases": ["..."]
  },
  "rerank_debug": {
    "candidate_count": 24,
    "selected_pmids": ["38291045", "37854321", "..."],
    "reasons": {
      "38291045": "Directly examines statin use and all-cause mortality in T2DM patients aged 65+.",
      "37854321": "Large cohort study of cardiovascular outcomes in elderly diabetic statin users."
    },
    "scores": { "38291045": 94, "37854321": 87 },
    "fallback_used": false
  }
}
```

### Smoke test — re-ranking with `include_debug: true`

```bash
curl -s -X POST http://localhost:8000/copilot/run \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Does statin use reduce all-cause mortality in elderly patients with type 2 diabetes?",
    "context": "Retrospective cohort using EHR data, adults aged 65+",
    "retmax": 6,
    "include_debug": true
  }' | python3 -m json.tool
```

**What to verify in the output:**

1. `rerank_debug.candidate_count` should be 20–40 (e.g. 24 for `retmax=6`).
2. `rerank_debug.selected_pmids` should list exactly `retmax` (6) PMIDs.
3. `rerank_debug.reasons` should contain one sentence per selected PMID.
4. `rerank_debug.fallback_used` should be `false` on a healthy run.
5. `articles` should contain exactly `retmax` (6) items, matching `selected_pmids`.
6. `analysis_plan.exposure_modeling` should list ≥ 2 strategies.
7. `analysis_plan.time_zero_definition`, `exposure_window`, `outcome_window` should all be non-null.
8. `literature_summaries[*].adjustment_set` should be populated but is NOT reflected verbatim in `key_confounders`.

### Minimal curl example (no debug)

```bash
curl -s -X POST http://localhost:8000/copilot/run \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Does statin use reduce all-cause mortality in elderly patients with type 2 diabetes?",
    "retmax": 6
  }' | python3 -m json.tool
```

### Testing in Swagger UI

1. Open <http://localhost:8000/docs>
2. Click **POST /copilot/run** → **Try it out**
3. Paste the debug request body above (with `"include_debug": true`) and click **Execute**
4. Inspect `rerank_debug` and `analysis_plan` in the response

---

## Other endpoints (smoke tests)

### GET /health

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### POST /pubmed/search

```bash
curl -s -X POST http://localhost:8000/pubmed/search \
  -H "Content-Type: application/json" \
  -d '{"query": "statin cardiovascular mortality", "retmax": 5}' | python3 -m json.tool
```

### POST /plan

```bash
curl -s -X POST http://localhost:8000/plan \
  -H "Content-Type: application/json" \
  -d '{"question": "Does statin use reduce all-cause mortality in elderly patients with type 2 diabetes?"}' \
  | python3 -m json.tool
```

---

## Deployment (Render)

1. Push the repo to GitHub.
2. Create a new **Web Service** on [Render](https://render.com) pointing at the repo.
3. Render auto-detects `render.yaml`.
4. Set `OPENAI_API_KEY` in the Render dashboard — **never commit the key**.
5. Render builds the Docker image and starts the server on the assigned `$PORT`.
