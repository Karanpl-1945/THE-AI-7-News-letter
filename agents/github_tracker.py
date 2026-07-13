"""Tracks GitHub trending repos and new releases from watched frameworks."""

import os
import requests
from bs4 import BeautifulSoup
from github import Github
from datetime import datetime, timedelta
from typing import List, Dict, Any
import yaml


def _load_config() -> Dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "sources.yaml")
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def _scrape_github_trending(language: str = "python", since: str = "weekly") -> List[Dict[str, Any]]:
    """Scrape GitHub trending page (no official API exists)."""
    url = f"https://github.com/trending/{language}?since={since}"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "ai-newspaper-bot/1.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        repos = []

        for article in soup.select("article.Box-row")[:10]:
            name_tag = article.select_one("h2 a")
            desc_tag = article.select_one("p")
            stars_tag = article.select_one("a.Link--muted:nth-of-type(1)")
            stars_gained = article.select_one("span.d-inline-block.float-sm-right")

            if not name_tag:
                continue

            full_name = name_tag.get("href", "").strip("/")
            repos.append({
                "title": full_name,
                "description": desc_tag.get_text(strip=True) if desc_tag else "",
                "url": f"https://github.com/{full_name}",
                "stars_this_week": stars_gained.get_text(strip=True) if stars_gained else "N/A",
                "total_stars": stars_tag.get_text(strip=True) if stars_tag else "N/A",
                "source": "github_trending",
                "type": "trending_repo",
            })
        return repos
    except Exception as e:
        print(f"[GitHubTracker] Trending scrape error: {e}")
        return []


def _fetch_recent_releases(token: str, repos: List[str], days_back: int = 7) -> List[Dict[str, Any]]:
    """Fetch latest releases from watched repos using GitHub API."""
    g = Github(token) if token else Github()
    cutoff = datetime.now() - timedelta(days=days_back)
    releases = []

    for repo_name in repos:
        try:
            repo = g.get_repo(repo_name)
            latest = repo.get_latest_release()
            pub = latest.published_at

            if pub and pub.replace(tzinfo=None) >= cutoff:
                releases.append({
                    "title": f"{repo_name} — {latest.tag_name}",
                    "repo": repo_name,
                    "tag": latest.tag_name,
                    "description": (latest.body or "")[:500].replace("\n", " "),
                    "url": latest.html_url,
                    "docs_url": f"https://github.com/{repo_name}",
                    "published": pub.strftime("%Y-%m-%d"),
                    "stars": repo.stargazers_count,
                    "source": "github_releases",
                    "type": "framework_release",
                })
        except Exception:
            # No release this week — skip silently
            pass

    return releases


def fetch_github_trends() -> List[Dict[str, Any]]:
    cfg = _load_config()["github"]
    token = os.getenv("GITHUB_TOKEN", "")

    trending = _scrape_github_trending(
        language=cfg.get("trending_language", "python"),
        since=cfg.get("trending_since", "weekly"),
    )

    releases = _fetch_recent_releases(
        token=token,
        repos=cfg.get("watch_repos", []),
    )

    return trending + releases
