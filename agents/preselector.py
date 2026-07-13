"""Deterministic filtering, deduplication, ranking, and selection before Groq."""

from __future__ import annotations

import math
import os
import re
from datetime import date, datetime
from typing import Any, Dict, List
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml


DEFAULT_WEIGHTS = {
    "freshness": 0.25,
    "relevance": 0.30,
    "credibility": 0.15,
    "completeness": 0.10,
    "activity": 0.10,
    "reproducibility": 0.10,
}

INTEREST_ALIASES = {
    "llm": ("llm", "large language model", "language model", "transformer"),
    "llms": ("llm", "large language model", "language model", "transformer"),
    "agents": ("agent", "agentic", "multi-agent", "tool use"),
    "computer vision": ("computer vision", "vision", "image", "video", "multimodal"),
    "nlp": ("nlp", "natural language processing", "language model"),
    "reinforcement learning": ("reinforcement learning", "rl", "reward model"),
}


def _load_config() -> Dict[str, Any]:
    path = os.path.join(os.path.dirname(__file__), "..", "config", "sources.yaml")
    with open(path, encoding="utf-8") as config_file:
        return yaml.safe_load(config_file).get("preselection", {})


def _item_text(item: Dict[str, Any]) -> str:
    fields = [
        item.get("title", ""),
        item.get("abstract", ""),
        item.get("summary", ""),
        item.get("description", ""),
        item.get("changelog", ""),
        " ".join(item.get("categories", [])),
    ]
    return " ".join(str(field) for field in fields if field).lower()


def _published_date(item: Dict[str, Any]) -> date | None:
    try:
        return datetime.strptime(item.get("published", ""), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return date.today() if item.get("source") == "github_trending" else None


def _numeric_signal(item: Dict[str, Any]) -> float:
    raw = item.get("stars_this_week") or item.get("stars") or 0
    if isinstance(raw, (int, float)):
        return max(float(raw), 0.0)

    match = re.search(
        r"([0-9]+(?:\.[0-9]+)?)\s*([km]?)",
        str(raw).lower().replace(",", ""),
    )
    if not match:
        return 0.0
    multiplier = {"": 1, "k": 1_000, "m": 1_000_000}[match.group(2)]
    return float(match.group(1)) * multiplier


def _freshness(item: Dict[str, Any], today: date | None = None) -> float:
    published = _published_date(item)
    if not published:
        return 0.0
    age_days = max(0, ((today or date.today()) - published).days)
    return max(0.0, 1.0 - age_days / 14)


def _relevance(item: Dict[str, Any]) -> float:
    configured = os.getenv("USER_INTERESTS", "LLMs,agents,computer vision")
    interests = [interest.strip().lower() for interest in configured.split(",") if interest.strip()]
    if not interests:
        return 0.5

    text = _item_text(item)
    matches = 0
    for interest in interests:
        terms = INTEREST_ALIASES.get(interest, (interest,))
        if any(term in text for term in terms):
            matches += 1
    return matches / len(interests)


def _credibility(item: Dict[str, Any], config: Dict[str, Any]) -> float:
    configured = {
        str(source).lower(): float(score)
        for source, score in config.get("source_credibility", {}).items()
    }
    return configured.get(str(item.get("source", "")).lower(), 0.60)


def _completeness(item: Dict[str, Any]) -> float:
    content = (
        item.get("abstract")
        or item.get("summary")
        or item.get("description")
        or item.get("changelog")
        or ""
    )
    required = bool(item.get("title") and item.get("url"))
    return min(len(content) / 600, 1.0) * (1.0 if required else 0.5)


def _activity(item: Dict[str, Any]) -> float:
    # 100,000 stars maps to 1.0; logarithmic scaling prevents popularity
    # from overwhelming freshness and user relevance.
    return min(math.log10(1 + _numeric_signal(item)) / 5, 1.0)


def _reproducibility(item: Dict[str, Any]) -> float:
    if item.get("has_code"):
        return 1.0
    if item.get("docs_url") and item.get("repo"):
        return 0.9
    if item.get("repo") or item.get("source") in {"github_trending", "github_releases"}:
        return 0.7
    if item.get("pdf_url"):
        return 0.3
    return 0.0


def score_breakdown(
    item: Dict[str, Any],
    category: str,
    config: Dict[str, Any] | None = None,
) -> Dict[str, float]:
    """Return normalized evidence scores used by the deterministic ranker."""
    config = config or _load_config()
    return {
        "freshness": _freshness(item),
        "relevance": _relevance(item),
        "credibility": _credibility(item, config),
        "completeness": _completeness(item),
        "activity": _activity(item),
        "reproducibility": _reproducibility(item),
    }


def selection_score(
    item: Dict[str, Any],
    category: str = "news",
    config: Dict[str, Any] | None = None,
) -> float:
    """Calculate a reproducible category-specific score from 0 to 100."""
    config = config or _load_config()
    weights = {**DEFAULT_WEIGHTS, **config.get("weights", {}).get(category, {})}
    evidence = score_breakdown(item, category, config)
    weight_total = sum(float(value) for value in weights.values()) or 1.0
    weighted = sum(evidence[name] * float(weights.get(name, 0)) for name in evidence)
    return round(100 * weighted / weight_total, 2)


def _canonical_url(value: str) -> str:
    if not value:
        return ""
    parts = urlsplit(value.strip())
    query = urlencode([
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def _normalized_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _deduplicate(ranked: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove exact canonical-URL and normalized-title duplicates."""
    unique: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    for item in ranked:
        url = _canonical_url(str(item.get("url", "")))
        title = _normalized_title(str(item.get("title", "")))
        if (url and url in seen_urls) or (title and title in seen_titles):
            continue
        unique.append(item)
        if url:
            seen_urls.add(url)
        if title:
            seen_titles.add(title)
    return unique


def _ranked_copy(item: Dict[str, Any], category: str, config: Dict[str, Any]) -> Dict[str, Any]:
    evidence = score_breakdown(item, category, config)
    score = selection_score(item, category, config)
    strongest = sorted(evidence, key=evidence.get, reverse=True)[:3]
    return {
        **item,
        "_selection": {
            "score": score,
            "category": category,
            "breakdown": {name: round(value, 3) for name, value in evidence.items()},
            "reasons": strongest,
        },
    }


def select_items(
    items: List[Dict[str, Any]],
    limit: int,
    max_per_source: int | None = None,
    category: str = "news",
    config: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """Deduplicate and select high-scoring items with optional source diversity."""
    if limit <= 0:
        return []

    config = config or _load_config()
    ranked = sorted(
        (_ranked_copy(item, category, config) for item in items if item.get("title")),
        key=lambda item: (item["_selection"]["score"], item.get("title", "")),
        reverse=True,
    )
    ranked = _deduplicate(ranked)

    selected: List[Dict[str, Any]] = []
    deferred: List[Dict[str, Any]] = []
    source_counts: Dict[str, int] = {}

    for item in ranked:
        source = item.get("source", "unknown")
        if max_per_source and source_counts.get(source, 0) >= max_per_source:
            deferred.append(item)
            continue
        selected.append(item)
        source_counts[source] = source_counts.get(source, 0) + 1
        if len(selected) == limit:
            return selected

    # Prefer diversity, but fill unused budget if too few sources are available.
    selected.extend(deferred[: max(0, limit - len(selected))])
    return selected


def preselect_for_summarization(state: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Apply deterministic ranking and per-category LLM budgets."""
    config = _load_config()
    limits = config.get("limits", {})
    source_caps = config.get("max_per_source", {})
    categories = {
        "selected_papers": ("papers", "papers"),
        "selected_models": ("model_news", "models"),
        "selected_github": ("github_trends", "github"),
        "selected_news": ("news_items", "news"),
        "selected_frameworks": ("framework_updates", "frameworks"),
    }

    return {
        output_key: select_items(
            state.get(input_key, []),
            limit=int(limits.get(category, 0)),
            max_per_source=source_caps.get(category),
            category=category,
            config=config,
        )
        for output_key, (input_key, category) in categories.items()
    }
