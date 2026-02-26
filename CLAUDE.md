# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Research Copilot — a full-stack app with a **Python FastAPI backend** (`research-copilot/`) and a **Next.js frontend** (`ui/`). The backend implements a multi-step LLM pipeline that converts an epidemiological research question into a structured, Markdown-formatted analysis protocol (SAP/protocol draft).

## Backend (research-copilot/)

### Dev commands
```bash
cd research-copilot
pip install -r requirements.txt
# Requires OPENAI_API_KEY in research-copilot/.env
python -m uvicorn app.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

### Smoke test the primary endpoint
```bash
curl -s -X POST http://localhost:8000/copilot/run \
  -H "Content-Type: application/json" \
  -d '{"question": "Does statin use reduce all-cause mortality in elderly patients with type 2 diabetes?", "retmax": 6, "include_debug": true}' \
  | python3 -m json.tool
```

### Pipeline architecture (`app/copilot.py`)

`POST /copilot/run` is the primary endpoint. It executes five sequential/parallel steps:

```
A) LLM query translation  →  primary_query + fallback_query + concept dict
B) PubMed search (NCBI E-utilities, over-fetches 4× retmax, falls back to broader query if <3 results)
B2) LLM re-ranker (scores 0-100, picks top N; graceful fallback to PubMed order)
C) Per-article LLM summarisation (parallelised with asyncio)
D) Causal analysis plan generation (AnalysisPlan schema; confounder rules enforced)
E) Markdown report rendering (template-based, no raw JSON in output)
```

### Key modules

| File | Responsibility |
|------|---------------|
| `app/main.py` | FastAPI app, endpoint routing |
| `app/copilot.py` | Pipeline orchestration + Markdown report rendering |
| `app/schemas.py` | All Pydantic models (`CopilotRunRequest/Response`, `QueryTranslation`, `PubMedArticle`, `LitSummary`, `AnalysisPlan`, `RerankDebug`, etc.) |
| `app/planner.py` | LLM call for analysis plan generation |
| `app/pubmed.py` | Async NCBI E-utilities wrapper |
| `app/rerank.py` | LLM re-ranking with fallback |

### LLM usage pattern
All LLM calls use `openai.responses.parse()` with a Pydantic response schema for structured output. Model is `gpt-4o-mini`, temperature 0.1–0.2. Client is initialized from `OPENAI_API_KEY` in `.env` via `python-dotenv`.

### Endpoints (all must remain working)
- `GET /health` — health check
- `POST /copilot/run` — primary user-facing endpoint
- `POST /plan` — analysis plan only (no literature)
- `POST /pubmed/search` — raw PubMed search
- `POST /plan_with_literature` — plan + PubMed in parallel

### Deployment
Docker → Render.com. Config in `render.yaml` and `Dockerfile`. `OPENAI_API_KEY` is set in the Render dashboard, never committed. Requirements must be standard pinned versions (no `@ file://` or conda local paths).

## Frontend (ui/)

### Dev commands
```bash
cd ui
npm install
npm run dev        # http://localhost:3000
npm run build
npm run lint       # ESLint
```

### Environment configuration
Create `ui/.env.local`:
```
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
```
Falls back to `http://127.0.0.1:8000` if not set. The backend must be running before using the app.

### Architecture

Next.js 16 (app router) with Tailwind CSS v4. Single-page client component at `src/app/page.tsx`.

**CORS**: The frontend never calls the FastAPI backend directly. All API calls go through the Next.js proxy route at `/api/copilot`, which forwards to `${NEXT_PUBLIC_API_BASE}/copilot/run` server-side. This avoids browser CORS restrictions without modifying the backend.

### Key files

| File | Responsibility |
|------|---------------|
| `src/app/page.tsx` | Main client component — form inputs, API call, split layout, PDF export |
| `src/app/api/copilot/route.ts` | Next.js API proxy to FastAPI backend (CORS bypass) |
| `src/app/layout.tsx` | Root layout — metadata, dark bg via inline style (IMPORTANT: inline style guarantees dark background regardless of Turbopack CSS cache; do not remove) |
| `src/app/globals.css` | Tailwind v4 config, dark theme vars, aurora gradient, custom scrollbar |
| `src/components/Spinner.tsx` | Animated neon SVG spinner with glow filter |
| `src/types/html2pdf.d.ts` | Module declaration for `html2pdf.js` (no `@types/` package exists) |

### UI design
- **Theme**: Sci-fi dark aesthetic — base `#080b14`, neon cyan `#00e5ff`, neon purple `#c084fc`
- **Layout**: Split desktop (lg+): left input panel 38% / right report panel 62%; stacked on mobile
- **Cards**: Glassmorphism — `bg-white/[0.04] backdrop-blur-md border border-white/[0.08] rounded-2xl`
- **Markdown**: Dark prose via Tailwind arbitrary selectors (`[&_h1]:text-cyan-300`, etc.) — no `@tailwindcss/typography` plugin

### PDF export
`html2pdf.js` (client-side, dynamic import). A hidden off-screen `div#report-pdf-target` with white background and serif font renders the same `report_markdown` content — this produces a clean, readable PDF independent of the dark UI theme.

### Known CSS issue
Turbopack may serve a stale compiled CSS chunk during development. The `<body>` in `layout.tsx` uses an inline `style={{ backgroundColor: "#080b14" }}` to guarantee the dark background wins the cascade. If you modify `globals.css` and the change doesn't appear, restart the dev server (`npm run dev`).
