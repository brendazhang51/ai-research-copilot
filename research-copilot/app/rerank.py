"""
LLM-based article re-ranker.

Given a list of PubMed candidate articles and a research question, uses an LLM
to score and select the top N most relevant articles.

Falls back gracefully to PubMed's original ordering if the LLM call fails.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from openai import OpenAI

from .schemas import RerankDebug, RerankResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_RERANKER_SYSTEM = (
    "You are a biomedical relevance expert. Your task is to re-rank research "
    "articles by their relevance to a given clinical or epidemiological research question.\n\n"
    "Score each article 0–100 based on how closely it matches the question across:\n"
    "  • Population: does the study population match?\n"
    "  • Exposure / intervention: does it study the relevant exposure?\n"
    "  • Outcome: does it measure the outcome of interest?\n"
    "  • Study design quality: is the design appropriate for causal inference?\n\n"
    "Select ONLY the top N articles requested, ordered from most to least relevant.\n"
    "For each selected article provide:\n"
    "  - pmid: the exact PubMed ID string\n"
    "  - score: integer 0–100\n"
    "  - reason: one concise sentence explaining its relevance\n\n"
    "Return ONLY valid JSON strictly following the schema. Do not include articles "
    "beyond the requested top N."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rerank_articles(
    question: str,
    context: Optional[str],
    articles: List[dict],
    top_n: int,
    client: OpenAI,
) -> Tuple[List[dict], RerankDebug]:
    """Re-rank candidate articles by relevance to *question* and return top *top_n*.

    Parameters
    ----------
    question:  The user's research question.
    context:   Optional additional context (dataset, setting, etc.).
    articles:  List of article dicts from pubmed.fetch_articles().
    top_n:     How many articles to select (= the user's original retmax).
    client:    Initialised OpenAI client.

    Returns
    -------
    (selected_articles, debug_info)
        selected_articles — up to top_n dicts, in ranked order.
        debug_info        — RerankDebug with counts, PMIDs, reasons, scores.
    """
    if not articles:
        return [], RerankDebug(
            candidate_count=0,
            selected_pmids=[],
            fallback_used=False,
        )

    # Cap top_n to the number of candidates available
    top_n = min(top_n, len(articles))

    # Build compact representation — truncate abstracts to keep prompt small
    compact_blocks: List[str] = []
    for a in articles:
        abstract_snippet = (a.get("abstract") or "")[:800]
        compact_blocks.append(
            f"PMID: {a['pmid']}\n"
            f"Title: {a.get('title', '(no title)')}\n"
            f"Journal: {a.get('journal', '')} ({a.get('year', '')})\n"
            f"Abstract: {abstract_snippet}"
        )
    articles_text = "\n\n---\n\n".join(compact_blocks)

    user_content = f"Research question: {question}\n"
    if context:
        user_content += f"Context: {context}\n"
    user_content += (
        f"\nFrom the {len(articles)} candidate articles below, select and rank "
        f"the top {top_n} most relevant. Output exactly {top_n} items (or fewer "
        f"if there are not enough relevant articles).\n\n"
        f"Candidates:\n\n{articles_text}"
    )

    try:
        result = client.responses.parse(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": _RERANKER_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            text_format=RerankResult,
        )
        rerank_result: RerankResult = result.output_parsed

        # Build a lookup for fast article retrieval
        pmid_to_article = {a["pmid"]: a for a in articles}

        selected: List[dict] = []
        reasons: dict[str, str] = {}
        scores: dict[str, int] = {}

        for item in rerank_result.items[:top_n]:
            if item.pmid in pmid_to_article and item.pmid not in {a["pmid"] for a in selected}:
                selected.append(pmid_to_article[item.pmid])
                reasons[item.pmid] = item.reason
                scores[item.pmid] = item.score

        # If the LLM returned fewer than top_n valid PMIDs, pad with remaining candidates
        seen_pmids = {a["pmid"] for a in selected}
        for a in articles:
            if len(selected) >= top_n:
                break
            if a["pmid"] not in seen_pmids:
                selected.append(a)
                seen_pmids.add(a["pmid"])

        debug = RerankDebug(
            candidate_count=len(articles),
            selected_pmids=[a["pmid"] for a in selected],
            reasons=reasons,
            scores=scores,
            fallback_used=False,
        )
        return selected, debug

    except Exception as exc:
        logger.warning("Reranker LLM call failed (%s); falling back to PubMed order.", exc)
        selected = articles[:top_n]
        debug = RerankDebug(
            candidate_count=len(articles),
            selected_pmids=[a["pmid"] for a in selected],
            reasons={},
            scores={},
            fallback_used=True,
        )
        return selected, debug
