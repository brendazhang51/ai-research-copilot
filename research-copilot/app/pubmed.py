"""
PubMed integration via NCBI E-utilities.

Uses:
  - esearch to retrieve PMIDs matching a query
  - efetch to download article metadata as XML, parsed with lxml
"""

from __future__ import annotations

import httpx
from lxml import etree
from typing import List

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


async def search_pmids(query: str, retmax: int = 8) -> List[str]:
    """Return a list of PMIDs for the given PubMed query."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "retmode": "json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(ESEARCH_URL, params=params)
        response.raise_for_status()
    data = response.json()
    return data.get("esearchresult", {}).get("idlist", [])


def _text(element, xpath: str) -> str:
    """Extract stripped text from the first matching XPath node, or empty string."""
    nodes = element.xpath(xpath)
    if nodes:
        return (nodes[0].text or "").strip()
    return ""


def _parse_articles(xml_bytes: bytes) -> list[dict]:
    """Parse PubMed efetch XML and return a list of article dicts."""
    root = etree.fromstring(xml_bytes)
    articles = []

    for article_node in root.xpath("//PubmedArticle"):
        medline = article_node.find("MedlineCitation")
        if medline is None:
            continue

        pmid = _text(medline, "PMID")
        article = medline.find("Article")
        if article is None:
            continue

        title = _text(article, "ArticleTitle")
        journal = _text(article, "Journal/Title")

        # Year: prefer PubDate/Year, fall back to MedlineDate
        year_nodes = article.xpath("Journal/JournalIssue/PubDate/Year")
        if year_nodes:
            year = (year_nodes[0].text or "").strip()
        else:
            medline_date_nodes = article.xpath(
                "Journal/JournalIssue/PubDate/MedlineDate"
            )
            raw = (
                (medline_date_nodes[0].text or "").strip() if medline_date_nodes else ""
            )
            year = raw[:4] if raw else ""

        # Abstract: concatenate all AbstractText sections
        abstract_parts = article.xpath("Abstract/AbstractText")
        abstract = " ".join(
            (part.text or "").strip() for part in abstract_parts if part.text
        )

        # Authors
        author_nodes = article.xpath("AuthorList/Author")
        authors: list[str] = []
        for auth in author_nodes:
            last = _text(auth, "LastName")
            initials = _text(auth, "Initials")
            if last:
                authors.append(f"{last} {initials}".strip() if initials else last)
        authors_str = ", ".join(authors[:3])
        if len(authors) > 3:
            authors_str += " et al."

        citation = f"{authors_str}. {title} {journal}. {year}.".strip(". ") + "."

        articles.append(
            {
                "pmid": pmid,
                "title": title,
                "journal": journal,
                "year": year,
                "abstract": abstract,
                "citation": citation,
            }
        )

    return articles


async def fetch_articles(pmids: List[str]) -> list[dict]:
    """Fetch full article metadata for a list of PMIDs. Returns list of article dicts."""
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(EFETCH_URL, params=params)
        response.raise_for_status()

    return _parse_articles(response.content)


async def search_and_fetch(query: str, retmax: int = 8) -> tuple[List[str], list[dict]]:
    """Convenience wrapper: search PubMed then fetch article details."""
    pmids = await search_pmids(query, retmax)
    articles = await fetch_articles(pmids)
    return pmids, articles
