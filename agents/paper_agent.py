"""Fetches recent AI/ML research papers from ArXiv and Papers With Code."""

import arxiv
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

import yaml, os

def _load_config() -> Dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "sources.yaml")
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def fetch_arxiv_papers() -> List[Dict[str, Any]]:
    cfg = _load_config()["arxiv"]
    categories = cfg["categories"]
    max_results = cfg["max_results"]
    days_back = cfg["days_back"]

    query = " OR ".join(f"cat:{c}" for c in categories)
    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=max_results * 2,
        sort_by=arxiv.SortCriterion.LastUpdatedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    papers = []

    try:
        for result in client.results(search):
            if result.updated < cutoff:
                break
            papers.append({
                "title": result.title.strip(),
                "authors": [a.name for a in result.authors[:3]],
                "abstract": result.summary.replace("\n", " ")[:600],
                "url": result.entry_id,
                "pdf_url": result.pdf_url,
                "categories": result.categories,
                "published": result.published.strftime("%Y-%m-%d"),
                "source": "arxiv",
            })
            if len(papers) >= max_results:
                break
    except Exception as e:
        print(f"[PaperAgent] ArXiv error: {e}")

    return papers


def fetch_papers_with_code() -> List[Dict[str, Any]]:
    cfg = _load_config()["papers_with_code"]
    if not cfg.get("enabled"):
        return []

    try:
        resp = requests.get(
            "https://paperswithcode.com/api/v1/papers/",
            params={"ordering": "-paper__published", "page_size": cfg["limit"]},
            timeout=15,
            headers={"User-Agent": "ai-newspaper-bot/1.0"},
        )
        resp.raise_for_status()
        papers = []
        for item in resp.json().get("results", []):
            p = item.get("paper", {})
            papers.append({
                "title": p.get("title", ""),
                "authors": [],
                "abstract": p.get("abstract", "")[:600],
                "url": f"https://paperswithcode.com/paper/{p.get('id', '')}",
                "pdf_url": p.get("url_pdf", ""),
                "categories": [],
                "published": p.get("published", ""),
                "has_code": True,
                "stars": item.get("stars", 0),
                "source": "paperswithcode",
            })
        return papers
    except Exception as e:
        print(f"[PaperAgent] PapersWithCode error: {e}")
        return []


def fetch_papers() -> List[Dict[str, Any]]:
    arxiv_papers = fetch_arxiv_papers()
    pwc_papers = fetch_papers_with_code()

    # Deduplicate by title (case-insensitive)
    seen = {p["title"].lower() for p in arxiv_papers}
    unique_pwc = [p for p in pwc_papers if p["title"].lower() not in seen]

    return arxiv_papers + unique_pwc
