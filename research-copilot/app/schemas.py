from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class PlanRequest(BaseModel):
    question: str = Field(..., min_length=5, description="Research question in plain language")
    context: Optional[str] = Field(None, description="Optional background/context, e.g., dataset, setting, constraints")


class AnalysisPlan(BaseModel):
    population: str
    exposure: str
    comparator: Optional[str] = None
    outcome: str
    suggested_study_design: str
    primary_model: str
    key_confounders: List[str]
    sensitivity_analyses: List[str]
    potential_biases: List[str]
    # Causal/temporal structure (new fields — optional for backwards compat)
    time_zero_definition: Optional[str] = Field(None, description="Precise index date definition to anchor follow-up")
    exposure_window: Optional[str] = Field(None, description="Exposure measurement window relative to time zero")
    outcome_window: Optional[str] = Field(None, description="Outcome ascertainment window / follow-up duration")
    exposure_modeling: List[str] = Field(
        default_factory=list,
        description="At least two exposure modeling strategies (e.g., continuous+spline, categorical thresholds)",
    )


class PlanResponse(BaseModel):
    plan: AnalysisPlan


# ---------------------------------------------------------------------------
# PubMed schemas
# ---------------------------------------------------------------------------

class PubMedSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, description="PubMed search query string")
    retmax: int = Field(8, ge=1, le=30, description="Maximum number of results to return (1-30)")


class PubMedArticle(BaseModel):
    pmid: str
    title: str
    journal: str
    year: str
    abstract: str
    citation: str


class PubMedSearchResponse(BaseModel):
    pmids: List[str]
    articles: List[PubMedArticle]


# ---------------------------------------------------------------------------
# Plan-with-literature schemas
# ---------------------------------------------------------------------------

class PlanWithLiteratureRequest(BaseModel):
    question: str = Field(..., min_length=5, description="Research question in plain language")
    context: Optional[str] = Field(None, description="Optional background/context")
    pubmed_query: Optional[str] = Field(None, description="PubMed search query; defaults to the research question if omitted")
    retmax: int = Field(8, ge=1, le=30, description="Maximum PubMed results to fetch (1-30)")


class PlanWithLiteratureResponse(BaseModel):
    plan: AnalysisPlan
    literature: List[PubMedArticle]


# ---------------------------------------------------------------------------
# Copilot pipeline schemas
# ---------------------------------------------------------------------------

class QueryConcepts(BaseModel):
    """Key biomedical concepts extracted from the research question."""
    population: str = Field("", description="Target population keywords")
    exposure: str = Field("", description="Exposure/intervention keywords")
    outcome: str = Field("", description="Outcome keywords")


class QueryTranslation(BaseModel):
    """LLM-generated PubMed query plan from a natural-language research question."""
    primary_query: str = Field(..., description="Specific PubMed Boolean query")
    fallback_query: str = Field(..., description="Broader fallback PubMed query if primary returns few results")
    concepts: QueryConcepts = Field(default_factory=QueryConcepts)


class LitSummary(BaseModel):
    """Structured extraction from a single article abstract."""
    pmid: str = Field("", description="PubMed ID (set programmatically, not by LLM)")
    study_design: Optional[str] = Field(None, description="e.g., RCT, cohort, case-control")
    population: Optional[str] = Field(None, description="Study population description")
    exposure: Optional[str] = Field(None, description="Exposure or intervention studied")
    outcome: Optional[str] = Field(None, description="Primary outcome measured")
    model: Optional[str] = Field(None, description="Statistical model or analytical approach")
    key_finding: Optional[str] = Field(None, description="Single most important finding")
    adjustment_set: Optional[str] = Field(
        None,
        description=(
            "Variables the authors adjusted for, as reported in the paper. "
            "For context only — reflects the paper's choices, not necessarily valid causal confounders."
        ),
    )
    notes: Optional[str] = Field(None, description="Notes when abstract is missing or incomplete")


# ---------------------------------------------------------------------------
# Re-ranking schemas
# ---------------------------------------------------------------------------

class RerankItem(BaseModel):
    """A single re-ranked article result from the LLM reranker."""
    pmid: str = Field(..., description="PubMed ID")
    score: int = Field(..., ge=0, le=100, description="Relevance score 0-100")
    reason: str = Field(..., description="One-sentence explanation of relevance to the research question")


class RerankResult(BaseModel):
    """LLM re-ranking output: ordered list of selected relevant articles."""
    items: List[RerankItem] = Field(
        ..., description="Articles ordered from most to least relevant (top N only)"
    )


class RerankDebug(BaseModel):
    """Debug information from the re-ranking stage."""
    candidate_count: int = Field(..., description="Total candidates fetched from PubMed before re-ranking")
    selected_pmids: List[str] = Field(..., description="PMIDs selected after re-ranking, in ranked order")
    reasons: Dict[str, str] = Field(default_factory=dict, description="Per-PMID one-sentence relevance reason")
    scores: Dict[str, int] = Field(default_factory=dict, description="Per-PMID relevance score (0-100)")
    fallback_used: bool = Field(False, description="True if the LLM reranker failed and PubMed's original order was used")


class CopilotRunRequest(BaseModel):
    question: str = Field(..., min_length=5, description="Research question in plain language")
    context: Optional[str] = Field(None, description="Optional background/context")
    retmax: int = Field(6, ge=1, le=30, description="Maximum PubMed articles to retrieve (1-30)")
    include_debug: bool = Field(False, description="If true, include intermediate pipeline outputs in the response")


class CopilotRunResponse(BaseModel):
    report_markdown: str = Field(..., description="Full Markdown report ready for display")
    display_title: str = Field(..., description="Short title derived from the question (≤ 80 chars)")
    # Debug / detailed fields — only populated when include_debug=true
    pubmed_queries: Optional[QueryTranslation] = None
    articles: Optional[List[PubMedArticle]] = None
    literature_summaries: Optional[List[LitSummary]] = None
    analysis_plan: Optional[AnalysisPlan] = None
    rerank_debug: Optional[RerankDebug] = None
