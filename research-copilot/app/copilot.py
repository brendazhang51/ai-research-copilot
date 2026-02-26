"""
Copilot run pipeline.

Orchestrates five sequential/parallel steps:
  A) Query translation  (LLM)
  B) PubMed search with fallback — fetches MORE candidates than shown to user
  B2) Re-ranking — LLM scores candidates, selects top N by relevance
  C) Literature summarization per article (LLM, parallelised on selected articles only)
  D) Analysis plan generation informed by literature (LLM, causal confounder rules)
  E) Markdown report rendering (template)
"""

from __future__ import annotations

import asyncio
import os
from typing import Dict, List, Optional

from openai import OpenAI

from .pubmed import search_and_fetch
from .rerank import rerank_articles
from .schemas import (
    AnalysisPlan,
    CopilotRunResponse,
    LitSummary,
    PubMedArticle,
    QueryTranslation,
    RerankDebug,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in environment variables.")
    return OpenAI(api_key=api_key)


# ---------------------------------------------------------------------------
# Step A: Query translator
# ---------------------------------------------------------------------------

_QUERY_TRANSLATOR_SYSTEM = (
    "You are a biomedical librarian expert in PubMed Boolean search syntax.\n"
    "Given a clinical research question, output:\n"
    "  primary_query  – a specific, MeSH-enriched PubMed query\n"
    "  fallback_query – a shorter, broader query for when primary yields few results\n"
    "  concepts       – key population, exposure, and outcome keywords\n"
    "Return ONLY structured output matching the schema."
)


def translate_to_pubmed_query(
    question: str, context: Optional[str], client: OpenAI
) -> QueryTranslation:
    user = f"Research question: {question}"
    if context:
        user += f"\nContext: {context}"

    result = client.responses.parse(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": _QUERY_TRANSLATOR_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        text_format=QueryTranslation,
    )
    return result.output_parsed


# ---------------------------------------------------------------------------
# Step C: Literature summarizer (one article at a time, run in parallel)
# ---------------------------------------------------------------------------

_LIT_SUMMARIZER_SYSTEM = (
    "You are a clinical research analyst. Extract key methodological details "
    "from the article abstract. Be concise. If information is not stated, return null.\n\n"
    "Extract the following fields:\n"
    "  study_design   – type of study (RCT, prospective cohort, retrospective cohort, "
    "case-control, cross-sectional, meta-analysis, systematic review, etc.)\n"
    "  population     – study population characteristics (age, condition, setting)\n"
    "  exposure       – exposure or intervention studied\n"
    "  outcome        – primary outcome(s) measured\n"
    "  model          – statistical model or analytical approach used\n"
    "  key_finding    – single most important finding or effect estimate with direction and magnitude\n"
    "  adjustment_set – variables the AUTHORS adjusted for, exactly as described in the paper "
    "(free text, e.g. 'age, sex, BMI, baseline HbA1c, eGFR'). "
    "This reflects the paper's own analytic choices and is provided for CONTEXT ONLY — "
    "it is NOT a canonical list of valid causal confounders for a new study.\n\n"
    "IMPORTANT: Do not conflate adjustment_set with causal confounders. "
    "Papers may adjust for disease-severity proxies, biomarkers, or treatment-indication "
    "variables that are not necessarily transferable to another analysis."
)


def _summarize_one(article: dict, client: OpenAI) -> LitSummary:
    pmid = article.get("pmid", "")
    abstract = article.get("abstract", "")

    if not abstract:
        return LitSummary(pmid=pmid, notes="No abstract available.")

    user = (
        f"Title: {article.get('title', '')}\n"
        f"Journal: {article.get('journal', '')} ({article.get('year', '')})\n"
        f"Abstract: {abstract}"
    )

    result = client.responses.parse(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": _LIT_SUMMARIZER_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
        text_format=LitSummary,
    )
    parsed: LitSummary = result.output_parsed
    parsed.pmid = pmid  # always overwrite with the real PMID from source data
    return parsed


# ---------------------------------------------------------------------------
# Step D: Analysis plan informed by literature
# ---------------------------------------------------------------------------

_PLAN_SYSTEM = (
    "You are a senior biostatistician and clinical epidemiologist.\n"
    "Given a research question and a brief summary of the relevant literature, "
    "produce a rigorous SAP-style analysis plan.\n\n"

    "=== CONFOUNDER RULES (CRITICAL) ===\n"
    "key_confounders must satisfy ALL of the following criteria:\n"
    "  1. Pre-exposure: the variable must be measured BEFORE the exposure is assigned "
    "(no post-exposure mediators or colliders).\n"
    "  2. Causal pathway: the variable must plausibly affect BOTH exposure selection "
    "AND the outcome through independent pathways (classical confounding criterion).\n"
    "  3. Clinical justification: ground each confounder in clinical or biological "
    "reasoning (e.g., severity of illness, baseline comorbidities, care intensity, "
    "healthcare utilisation, demographic risk factors) — NOT in what a paper happened to adjust for.\n"
    "  4. Separate confounders from predictors: a variable that predicts the outcome "
    "but is unrelated to exposure assignment is a precision variable, NOT a confounder; "
    "omit it from key_confounders.\n"
    "  5. Do NOT copy biomarkers, disease-severity scores, or paper-specific predictors "
    "into key_confounders unless they clearly satisfy criteria 1–3 for THIS question.\n\n"

    "=== REQUIRED PLAN ELEMENTS ===\n"
    "  time_zero_definition  – Define the precise index date that anchors follow-up "
    "(e.g., 'first dispensing of drug X ≥ 30 days after diagnosis Y').\n"
    "  exposure_window       – Define how and when exposure is measured relative to time zero "
    "(e.g., '−30 to 0 days before index date').\n"
    "  outcome_window        – Define the follow-up period for outcome ascertainment "
    "(e.g., '1–365 days after time zero').\n"
    "  exposure_modeling     – Specify AT LEAST TWO analytic forms:\n"
    "    a) Continuous with restricted cubic spline (state number of knots and placement, "
    "e.g., '3-knot RCS at 10th, 50th, 90th percentiles')\n"
    "    b) Categorical thresholds (e.g., clinical cut-points or quartiles)\n"
    "    c) Threshold sensitivity: pre-specify at least one alternate cut-point.\n\n"

    "Return structured output strictly following the schema."
)


def _generate_plan_with_lit(
    question: str,
    context: Optional[str],
    lit_summaries: List[LitSummary],
    client: OpenAI,
) -> AnalysisPlan:
    lit_lines: List[str] = []
    for s in lit_summaries:
        parts = [f"PMID {s.pmid}"]
        if s.study_design:
            parts.append(f"design: {s.study_design}")
        if s.population:
            parts.append(f"population: {s.population}")
        if s.exposure:
            parts.append(f"exposure: {s.exposure}")
        if s.outcome:
            parts.append(f"outcome: {s.outcome}")
        if s.key_finding:
            parts.append(f"finding: {s.key_finding}")
        # Include adjustment_set as labelled context — clearly NOT confounders
        if s.adjustment_set:
            parts.append(
                f"[paper's adjustment set — context only, do NOT copy into confounders: "
                f"{s.adjustment_set}]"
            )
        lit_lines.append("; ".join(parts))

    user = f"Research question: {question}"
    if context:
        user += f"\nContext: {context}"
    if lit_lines:
        user += (
            "\n\nRelevant literature (use to inform design choices and evidence gaps; "
            "do NOT copy paper-specific adjustment sets into key_confounders — "
            "apply the confounder rules from your instructions):\n"
            + "\n".join(lit_lines)
        )

    result = client.responses.parse(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": _PLAN_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        text_format=AnalysisPlan,
    )
    return result.output_parsed


# ---------------------------------------------------------------------------
# Step E: Markdown report renderer (template-based, no extra LLM call)
# ---------------------------------------------------------------------------

def _render_report(
    question: str,
    display_title: str,
    plan: AnalysisPlan,
    articles: List[dict],
    lit_summaries: List[LitSummary],
    queries: QueryTranslation,
    rerank_debug: Optional[RerankDebug] = None,
) -> str:
    lines: List[str] = []

    lines += [f"# {display_title}", ""]

    lines += ["## Research Question", "", question, ""]

    candidate_count = rerank_debug.candidate_count if rerank_debug else len(articles)
    lines += [
        "## PubMed Search",
        "",
        f"- **Primary query:** `{queries.primary_query}`",
        f"- **Fallback query:** `{queries.fallback_query}`",
        f"- **Candidates fetched:** {candidate_count}",
        f"- **Articles after re-ranking:** {len(articles)}",
        "",
    ]

    lines += ["## Key Papers", ""]
    if articles:
        reasons: Dict[str, str] = rerank_debug.reasons if rerank_debug else {}
        for a in articles:
            pmid = a.get("pmid", "")
            line = f"- {a.get('citation', '')} [PMID: {pmid}]"
            if reasons.get(pmid):
                line += f"  \n  *Relevance: {reasons[pmid]}*"
            lines.append(line)
    else:
        lines.append("- No articles retrieved for this query.")
    lines.append("")

    lines += ["## Evidence Summary", ""]
    summaries_with_findings = [s for s in lit_summaries if s.key_finding or s.notes]
    if summaries_with_findings:
        for s in summaries_with_findings:
            design_tag = f" *(design: {s.study_design})*" if s.study_design else ""
            finding = s.key_finding or s.notes or ""
            lines.append(f"- **[PMID {s.pmid}]**{design_tag}: {finding}")
    else:
        lines.append("- Insufficient abstracts to summarise individual studies.")
    lines.append("")

    lines += ["## Proposed Analysis Plan", ""]
    lines.append(f"- **Population:** {plan.population}")
    lines.append(f"- **Exposure:** {plan.exposure}")
    if plan.comparator:
        lines.append(f"- **Comparator:** {plan.comparator}")
    lines.append(f"- **Outcome:** {plan.outcome}")
    lines.append(f"- **Study design:** {plan.suggested_study_design}")

    if plan.time_zero_definition:
        lines.append(f"- **Time zero:** {plan.time_zero_definition}")
    if plan.exposure_window:
        lines.append(f"- **Exposure window:** {plan.exposure_window}")
    if plan.outcome_window:
        lines.append(f"- **Outcome window:** {plan.outcome_window}")

    lines.append(f"- **Primary model:** {plan.primary_model}")
    lines.append("")

    if plan.exposure_modeling:
        lines.append("**Exposure modeling strategies:**")
        for em in plan.exposure_modeling:
            lines.append(f"  - {em}")
        lines.append("")

    if plan.key_confounders:
        lines.append("**Key confounders to adjust for:**")
        for c in plan.key_confounders:
            lines.append(f"  - {c}")
        lines.append("")

    lines += ["## Sensitivity Analyses", ""]
    for s in (plan.sensitivity_analyses or ["None specified."]):
        lines.append(f"- {s}")
    lines.append("")

    lines += ["## Potential Biases & Limitations", ""]
    for b in (plan.potential_biases or ["None specified."]):
        lines.append(f"- {b}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_pipeline(
    question: str,
    context: Optional[str],
    retmax: int,
    include_debug: bool,
) -> CopilotRunResponse:
    client = _client()

    # A) Translate question → PubMed queries
    queries = await asyncio.to_thread(
        translate_to_pubmed_query, question, context, client
    )

    # B) PubMed search — fetch MORE candidates than retmax, then re-rank down to retmax.
    #    retmax_candidates = min(max(retmax*4, 20), 40)
    retmax_candidates = min(max(retmax * 4, 20), 40)

    pmids, raw_candidates = await search_and_fetch(queries.primary_query, retmax_candidates)

    # Fall back to broader query when primary returns fewer than 3 results
    if len(pmids) < 3:
        fb_pmids, fb_articles = await search_and_fetch(queries.fallback_query, retmax_candidates)
        seen = set(pmids)
        for pmid, art in zip(fb_pmids, fb_articles):
            if pmid not in seen:
                pmids.append(pmid)
                raw_candidates.append(art)
                seen.add(pmid)

    # B2) Re-rank candidates with LLM; select top N = retmax
    raw_articles, rerank_debug = await asyncio.to_thread(
        rerank_articles, question, context, raw_candidates, retmax, client
    )

    # C) Summarise each *selected* article in parallel (not all candidates)
    lit_summaries: List[LitSummary] = list(
        await asyncio.gather(
            *[asyncio.to_thread(_summarize_one, art, client) for art in raw_articles]
        )
    )

    # D) Generate analysis plan informed by literature summaries
    plan = await asyncio.to_thread(
        _generate_plan_with_lit, question, context, lit_summaries, client
    )

    # E) Render Markdown report
    display_title = question[:77].rstrip() + ("..." if len(question) > 80 else "")
    report = _render_report(
        question,
        display_title,
        plan,
        raw_articles,
        lit_summaries,
        queries,
        rerank_debug=rerank_debug,
    )

    return CopilotRunResponse(
        report_markdown=report,
        display_title=display_title,
        pubmed_queries=queries if include_debug else None,
        articles=[PubMedArticle(**a) for a in raw_articles] if include_debug else None,
        literature_summaries=lit_summaries if include_debug else None,
        analysis_plan=plan if include_debug else None,
        rerank_debug=rerank_debug if include_debug else None,
    )
