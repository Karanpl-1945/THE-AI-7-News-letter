"""Groq-powered editor that produces the complete editorial package in one call."""

import json
import os
from typing import Any, Dict, List

from langfuse import observe
from llm.groq_client import GroqRateLimitError, get_groq_gateway


CATEGORY_SPECS = {
    "top_papers": ("summarized_papers", 5, "Research Paper"),
    "top_models": ("summarized_models", 3, "Model Release"),
    "top_github": ("summarized_github", 5, "GitHub"),
    "top_frameworks": ("summarized_frameworks", 3, "Framework"),
    "top_news": ("summarized_news", 4, "News"),
}

PAPER_FEATURE_FIELDS = (
    "problem",
    "approach",
    "results",
    "implications",
    "why_you_should_care",
)
TOOL_FEATURE_FIELDS = (
    "what_it_is",
    "whats_new",
    "comparison",
    "install_cmd",
    "quickstart_code",
    "who_should_use",
)


@observe(name="groq_editor_call", as_type="chain")
def _call(prompt: str, max_tokens: int = 1800) -> Dict[str, Any]:
    return get_groq_gateway().create_json_completion(
        prompt=prompt,
        model=os.getenv("GROQ_EDITOR_MODEL", "llama-3.3-70b-versatile"),
        max_tokens=max_tokens,
    )


def _select_top_items(state: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Use the deterministic preselector order instead of another LLM call."""
    return {
        output_key: list(state.get(state_key, []))[:limit]
        for output_key, (state_key, limit, _label) in CATEGORY_SPECS.items()
    }


def _compact_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the consolidated prompt useful without resending entire source records."""
    return {
        "title": item.get("title", ""),
        "summary": (
            item.get("summary")
            or item.get("abstract")
            or item.get("description")
            or item.get("changelog")
            or ""
        )[:350],
        "why_it_matters": item.get("why_it_matters", "")[:200],
        "key_takeaway": item.get("key_takeaway", "")[:160],
        "url": item.get("url", ""),
        "docs_url": item.get("docs_url", ""),
        "difficulty": item.get("difficulty", "Intermediate"),
        "tags": list(item.get("tags", []))[:4],
    }


def _prompt_payload(top_items: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    return {
        CATEGORY_SPECS[key][2]: [_compact_item(item) for item in items]
        for key, items in top_items.items()
    }


def _build_prompt(top_items: Dict[str, List[Dict[str, Any]]], editorial_feedback: str | None = None) -> str:
    payload = json.dumps(_prompt_payload(top_items), ensure_ascii=False)
    feedback_block = ""
    if editorial_feedback:
        feedback_block = (
            f"\nThe admin reviewed the previous draft and requested: {editorial_feedback}\n"
            f"Address this feedback directly in your selections and writing.\n"
        )
    return f"""You are the editor of THE AI 7 weekly AI intelligence brief.
The stories below were already filtered, deduplicated, ranked, and ordered by a deterministic system.
Do not re-rank them. Use only the supplied evidence; do not invent benchmarks, URLs, releases, or claims.

User interests: {os.getenv('USER_INTERESTS', 'LLMs, agents')}
Skill level: {os.getenv('SKILL_LEVEL', 'intermediate')}
{feedback_block}
SELECTED STORIES:
{payload}

Produce the complete editorial package in ONE response. Return ONLY valid JSON with this exact shape:
{{
  "tldr": [
    "[Research Paper] one evidence-grounded sentence",
    "[Model Release] one evidence-grounded sentence",
    "[GitHub] one evidence-grounded sentence",
    "[Framework] one evidence-grounded sentence",
    "[News] one evidence-grounded sentence"
  ],
  "editors_pick_title": "exact title of the single most important supplied story",
  "editors_pick_reason": "2 concise sentences explaining its importance",
  "paper_of_week": {{
    "problem": "2 sentences",
    "approach": "2 concise sentences",
    "results": "1-2 sentences; say evidence not supplied when necessary",
    "implications": "2 sentences",
    "why_you_should_care": "1 sentence"
  }},
  "tool_of_week": {{
    "what_it_is": "2 sentences",
    "whats_new": "2 sentences based only on supplied evidence",
    "comparison": "2 sentences; state when prior-version evidence is unavailable",
    "install_cmd": "one command, or an empty string when unknown",
    "quickstart_code": "short Python example, or an empty string when unsupported by evidence",
    "who_should_use": "1 sentence"
  }},
  "glossary": [
    {{"term": "term", "definition": "one-sentence definition"}},
    {{"term": "term", "definition": "one-sentence definition"}},
    {{"term": "term", "definition": "one-sentence definition"}},
    {{"term": "term", "definition": "one-sentence definition"}},
    {{"term": "term", "definition": "one-sentence definition"}}
  ],
  "learning_paths": ["path 1", "path 2", "path 3"],
  "trending_topics": ["topic1", "topic2", "topic3", "topic4", "topic5", "topic6", "topic7", "topic8"]
}}"""


def _fallback_tldr(top_items: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    bullets = []
    for key, (_state_key, _limit, label) in CATEGORY_SPECS.items():
        if top_items[key]:
            item = top_items[key][0]
            text = item.get("key_takeaway") or item.get("summary") or item.get("title", "")
            bullets.append(f"[{label}] {str(text)[:220]}")
    return bullets


def _fallback_package(top_items: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    first_story = next((items[0] for items in top_items.values() if items), {})
    return {
        "tldr": _fallback_tldr(top_items),
        "editors_pick_title": first_story.get("title", ""),
        "editors_pick_reason": first_story.get("why_it_matters", ""),
        "paper_of_week": {},
        "tool_of_week": {},
        "glossary": [],
        "learning_paths": [],
        "trending_topics": [],
    }


def _clean_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _clean_feature(value: Any, allowed_fields: tuple[str, ...]) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        field: value[field].strip()
        for field in allowed_fields
        if isinstance(value.get(field), str) and value[field].strip()
    }


def _clean_glossary(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        if not isinstance(item, dict):
            continue
        term = item.get("term")
        definition = item.get("definition")
        if isinstance(term, str) and term.strip() and isinstance(definition, str) and definition.strip():
            cleaned.append({"term": term.strip(), "definition": definition.strip()})
    return cleaned


def _normalize_generated_package(
    generated: Dict[str, Any],
    top_items: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Keep valid editorial fields and fill malformed/missing fields safely."""
    fallback = _fallback_package(top_items)
    normalized = dict(fallback)
    usable_fields = 0

    for key in ("editors_pick_title", "editors_pick_reason"):
        value = generated.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()
            usable_fields += 1

    list_fields = {
        "tldr": 5,
        "learning_paths": 3,
        "trending_topics": 8,
    }
    for key, limit in list_fields.items():
        value = _clean_string_list(generated.get(key))[:limit]
        if value:
            normalized[key] = value
            usable_fields += 1

    glossary = _clean_glossary(generated.get("glossary"))[:5]
    if glossary:
        normalized["glossary"] = glossary
        usable_fields += 1

    paper_feature = _clean_feature(
        generated.get("paper_of_week"),
        PAPER_FEATURE_FIELDS,
    )
    if paper_feature:
        normalized["paper_of_week"] = paper_feature
        usable_fields += 1

    tool_feature = _clean_feature(
        generated.get("tool_of_week"),
        TOOL_FEATURE_FIELDS,
    )
    if tool_feature:
        normalized["tool_of_week"] = tool_feature
        usable_fields += 1

    if usable_fields == 0:
        raise ValueError("Editorial response contains no usable fields")
    return normalized


def _source_anchored_features(
    generated: Dict[str, Any],
    top_items: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Attach trusted titles and URLs rather than accepting LLM-generated links."""
    paper = top_items["top_papers"][0] if top_items["top_papers"] else {}
    tools = top_items["top_frameworks"] + top_items["top_github"]
    tool = tools[0] if tools else {}

    paper_feature = generated.get("paper_of_week")
    if not isinstance(paper_feature, dict):
        paper_feature = {}
    tool_feature = generated.get("tool_of_week")
    if not isinstance(tool_feature, dict):
        tool_feature = {}

    if paper:
        paper_feature = {
            **paper_feature,
            "title": paper.get("title", ""),
            "url": paper.get("url", ""),
            "difficulty": paper.get("difficulty", "Advanced"),
        }
    if tool:
        tool_feature = {
            **tool_feature,
            "name": tool.get("title", ""),
            "url": tool.get("url", ""),
            "docs_url": tool.get("docs_url", tool.get("url", "")),
        }

    return {"paper_of_week": paper_feature, "tool_of_week": tool_feature}


def _list_value(data: Dict[str, Any], key: str) -> List[Any]:
    value = data.get(key, [])
    return value if isinstance(value, list) else []


@observe(name="create_editorial", as_type="agent")
def create_editorial(state: Dict[str, Any]) -> Dict[str, Any]:
    print("[Editor] Using deterministic ranking for top items...")
    top_items = _select_top_items(state)
    print("[Editor] Generating the complete editorial package in one Groq call...")
    editorial_feedback = state.get("editorial_feedback")

    try:
        generated = _call(_build_prompt(top_items, editorial_feedback), max_tokens=1800)
        if not isinstance(generated, dict):
            raise ValueError("Editorial response must be a JSON object")
        generated = _normalize_generated_package(generated, top_items)
    except GroqRateLimitError as error:
        wait = error.retry_after_seconds
        retry_hint = f" Retry after approximately {wait:.0f} seconds." if wait else ""
        print(f"[Editor] Groq rate limit stopped editorial generation.{retry_hint}")
        raise
    except Exception as error:
        print(f"[Editor] Consolidated editorial failed: {error}")
        generated = _fallback_package(top_items)

    anchored = _source_anchored_features(generated, top_items)
    top_paper_titles = {paper.get("title", "") for paper in top_items["top_papers"]}
    more_papers = [
        paper
        for paper in state.get("summarized_papers", [])
        if paper.get("title", "") not in top_paper_titles
    ][:4]

    return {
        **top_items,
        "tldr": _list_value(generated, "tldr")[:5],
        "editors_pick_title": generated.get("editors_pick_title", ""),
        "editors_pick_reason": generated.get("editors_pick_reason", ""),
        **anchored,
        "glossary": _list_value(generated, "glossary")[:5],
        "learning_paths": _list_value(generated, "learning_paths")[:3],
        "trending_topics": _list_value(generated, "trending_topics")[:8],
        "more_papers": more_papers,
    }
