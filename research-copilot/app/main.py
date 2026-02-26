import os
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from .schemas import (
    PlanRequest,
    PlanResponse,
    PubMedSearchRequest,
    PubMedSearchResponse,
    PubMedArticle,
    PlanWithLiteratureRequest,
    PlanWithLiteratureResponse,
    CopilotRunRequest,
    CopilotRunResponse,
)
from .planner import generate_plan
from .pubmed import search_and_fetch
from .copilot import run_pipeline

load_dotenv()

app = FastAPI(
    title="AI Research Copilot (v0.3)",
    description=(
        "Generate structured epidemiological analysis plans and search PubMed "
        "for relevant literature. Use POST /copilot/run for the full one-click pipeline."
    ),
    version="0.3.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/plan", response_model=PlanResponse)
def create_plan(payload: PlanRequest):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set. Put it in .env")

    try:
        plan = generate_plan(payload.question, payload.context)
        return {"plan": plan}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate plan: {str(e)}")


@app.post("/pubmed/search", response_model=PubMedSearchResponse)
async def pubmed_search(payload: PubMedSearchRequest):
    """Search PubMed and return PMIDs plus article metadata."""
    try:
        pmids, raw_articles = await search_and_fetch(payload.query, payload.retmax)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"PubMed request failed: {str(e)}")

    articles = [PubMedArticle(**a) for a in raw_articles]
    return PubMedSearchResponse(pmids=pmids, articles=articles)


@app.post("/plan_with_literature", response_model=PlanWithLiteratureResponse)
async def plan_with_literature(payload: PlanWithLiteratureRequest):
    """Generate an analysis plan and fetch relevant PubMed literature in parallel."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set. Put it in .env")

    pubmed_query = payload.pubmed_query or payload.question

    try:
        plan_coro = asyncio.to_thread(generate_plan, payload.question, payload.context)
        pubmed_coro = search_and_fetch(pubmed_query, payload.retmax)
        plan, (_, raw_articles) = await asyncio.gather(plan_coro, pubmed_coro)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")

    articles = [PubMedArticle(**a) for a in raw_articles]
    return PlanWithLiteratureResponse(plan=plan, literature=articles)


@app.post("/copilot/run", response_model=CopilotRunResponse)
async def copilot_run(payload: CopilotRunRequest):
    """
    One-click research copilot pipeline.

    Internally executes:
    1. LLM query translation → PubMed Boolean queries
    2. PubMed search (with automatic fallback if results are sparse)
    3. Per-article literature summarisation (LLM, parallelised)
    4. Analysis plan generation informed by the literature (LLM)
    5. Markdown report rendering

    Set `include_debug=true` to receive intermediate outputs
    (pubmed_queries, articles, literature_summaries, analysis_plan).
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set. Put it in .env")

    try:
        return await run_pipeline(
            question=payload.question,
            context=payload.context,
            retmax=payload.retmax,
            include_debug=payload.include_debug,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Copilot pipeline failed: {str(e)}")
