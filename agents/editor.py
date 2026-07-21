"""Groq-powered editor: a core call for must-have content, a separate call for extras.

Splitting into two independent Groq calls means a failure in the "extras" call
(Research Radar, Emerging Patterns, Quick Hits, ...) never takes down the
must-have "core" content (TL;DR, Paper of the Week, Tool of the Week) — and
vice versa. Each has its own fallback, mirroring the existing per-item
fallback pattern in agents/summarizer.py.
"""

import json
import os
from typing import Any, Dict, List

from langfuse import observe
from llm.groq_client import GroqRateLimitError, get_groq_gateway

from agents.preselector import _canonical_url, _normalized_title


CATEGORY_SPECS = {
    "top_papers": ("summarized_papers", 5, "Research Paper"),
    "top_models": ("summarized_models", 3, "Model Release"),
    "top_github": ("summarized_github", 5, "GitHub"),
    "top_frameworks": ("summarized_frameworks", 3, "Framework"),
    "top_news": ("summarized_news", 4, "News"),
}

# Maps each raw/selected state key pair used to find leftover (not-selected) items.
LEFTOVER_SOURCE_MAP = {
    "papers": "selected_papers",
    "model_news": "selected_models",
    "github_trends": "selected_github",
    "news_items": "selected_news",
    "framework_updates": "selected_frameworks",
}
LEFTOVER_CAP_PER_CATEGORY = 8

PAPER_FEATURE_FIELDS = (
    "problem",
    "approach",
    "results",
    "why_you_should_care",
    "takeaway",
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
def _call(prompt: str, max_tokens: int) -> Dict[str, Any]:
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
    """Keep prompts useful without resending entire source records."""
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


def _leftover_items(
    full_items: List[Dict[str, Any]],
    selected_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Items collected this week but cut by the preselector's top-N limit.

    Reuses the same canonical-URL/normalized-title matching the preselector
    already applies for dedup, so "leftover" means genuinely not selected,
    not just a different object with the same content.
    """
    selected_urls = {_canonical_url(str(i.get("url", ""))) for i in selected_items}
    selected_titles = {_normalized_title(str(i.get("title", ""))) for i in selected_items}

    leftover = []
    for item in full_items:
        if not item.get("title"):
            continue
        url = _canonical_url(str(item.get("url", "")))
        title = _normalized_title(str(item.get("title", "")))
        if (url and url in selected_urls) or (title and title in selected_titles):
            continue
        leftover.append(item)
    return leftover[:LEFTOVER_CAP_PER_CATEGORY]


def _collect_leftovers(state: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        raw_key: _leftover_items(state.get(raw_key, []), state.get(selected_key, []))
        for raw_key, selected_key in LEFTOVER_SOURCE_MAP.items()
    }


def _prompt_payload(top_items: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    return {
        CATEGORY_SPECS[key][2]: [_compact_item(item) for item in items]
        for key, items in top_items.items()
    }


def _build_core_prompt(
    top_items: Dict[str, List[Dict[str, Any]]],
    editorial_feedback: str | None,
) -> str:
    payload = json.dumps(_prompt_payload(top_items), ensure_ascii=False)
    feedback_block = ""
    if editorial_feedback:
        feedback_block = (
            f"\nThe admin reviewed the previous draft and requested: {editorial_feedback}\n"
            f"Address this feedback directly in your selections and writing.\n"
        )
    return f"""You are the editor of THE AI 7 weekly AI intelligence brief, writing the must-have
opening content. The stories below were already filtered, deduplicated, ranked, and ordered by a
deterministic system. Do not re-rank them. Use only the supplied evidence; do not invent
benchmarks, URLs, releases, or claims.

User interests: {os.getenv('USER_INTERESTS', 'LLMs, agents')}
Skill level: {os.getenv('SKILL_LEVEL', 'intermediate')}
{feedback_block}
SELECTED STORIES:
{payload}

Produce ONLY valid JSON with this exact shape:
{{
  "tldr": [
    "[Research Paper] one evidence-grounded sentence",
    "[Model Release] one evidence-grounded sentence",
    "[GitHub] one evidence-grounded sentence",
    "[Framework] one evidence-grounded sentence",
    "[News] one evidence-grounded sentence"
  ],
  "paper_of_week": {{
    "problem": "2 sentences",
    "approach": "2 concise sentences",
    "results": "1-2 sentences; say evidence not supplied when necessary",
    "why_you_should_care": "1-2 sentences explaining why this is the week's most important story",
    "takeaway": "one concise sentence — the single most important thing to know"
  }},
  "tool_of_week": {{
    "what_it_is": "2 sentences",
    "whats_new": "2 sentences based only on supplied evidence",
    "comparison": "2 sentences; state when prior-version evidence is unavailable",
    "install_cmd": "one command, or an empty string when unknown",
    "quickstart_code": "short Python example, or an empty string when unsupported by evidence",
    "who_should_use": "1 sentence"
  }}
}}"""


def _build_extras_prompt(leftovers: Dict[str, List[Dict[str, Any]]]) -> str:
    payload = {
        "more_papers": [_compact_item(i) for i in leftovers["papers"]],
        "more_models": [_compact_item(i) for i in leftovers["model_news"]],
        "more_github": [_compact_item(i) for i in leftovers["github_trends"]],
        "more_news": [_compact_item(i) for i in leftovers["news_items"]],
        "more_frameworks": [_compact_item(i) for i in leftovers["framework_updates"]],
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    return f"""You are the editor of THE AI 7, writing the best-effort "extras" section of this
week's issue. These stories were NOT selected for the main sections. Use only the supplied
evidence; never invent facts, URLs, or claims. If nothing genuinely qualifies for a field, return
an empty list or empty string for it rather than forcing an answer.

ADDITIONAL STORIES:
{payload_json}

Produce ONLY valid JSON with this exact shape:
{{
  "research_radar": [
    {{"title": "exact title copied from the supplied stories", "one_liner": "one sentence: what concept or topic this advances"}}
  ],
  "emerging_patterns": [
    {{"title": "exact title copied from the supplied stories", "one_liner": "one sentence: the problem this solves better than before — only include items genuinely about RAG, retrieval, vector databases, or indexing"}}
  ],
  "production_playbook": {{
    "title": "exact title of one practical real-world build or postmortem from the supplied stories, or empty string if none fit",
    "summary": "2-3 practical sentences, or empty string if none fit"
  }},
  "under_the_radar": {{
    "title": "exact title of one non-obvious pick worth attention, or empty string if none fit",
    "reason": "1-2 sentences on why it deserves attention despite not trending, or empty string if none fit"
  }},
  "quick_hits": ["one-line mention", "one-line mention", "one-line mention"],
  "trending_topics": ["topic1", "topic2", "topic3"],
  "glossary": [
    {{"term": "term", "definition": "one-sentence definition"}}
  ],
  "learning_paths": ["path 1", "path 2", "path 3"]
}}"""


def _fallback_tldr(top_items: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    bullets = []
    for key, (_state_key, _limit, label) in CATEGORY_SPECS.items():
        if top_items[key]:
            item = top_items[key][0]
            text = item.get("key_takeaway") or item.get("summary") or item.get("title", "")
            bullets.append(f"[{label}] {str(text)[:220]}")
    return bullets


def _fallback_core_package(top_items: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    return {
        "tldr": _fallback_tldr(top_items),
        "paper_of_week": {},
        "tool_of_week": {},
    }


def _fallback_extras_package() -> Dict[str, Any]:
    return {
        "research_radar": [],
        "emerging_patterns": [],
        "production_playbook": {},
        "under_the_radar": {},
        "quick_hits": [],
        "trending_topics": [],
        "glossary": [],
        "learning_paths": [],
    }


def _clean_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _clean_feature(value: Any, allowed_fields: tuple) -> Dict[str, str]:
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


def _leftover_pool_flat(leftovers: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    flat = []
    for items in leftovers.values():
        flat.extend(items)
    return flat


def _find_by_title(title: Any, pool: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    if not isinstance(title, str) or not title.strip():
        return None
    normalized = _normalized_title(title)
    for item in pool:
        if _normalized_title(str(item.get("title", ""))) == normalized:
            return item
    return None


def _clean_radar_list(value: Any, pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only entries whose title matches a real supplied item — anchors the URL."""
    if not isinstance(value, list):
        return []
    cleaned = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        one_liner = entry.get("one_liner")
        if not isinstance(one_liner, str) or not one_liner.strip():
            continue
        matched = _find_by_title(entry.get("title"), pool)
        if not matched:
            continue
        cleaned.append({
            "title": matched.get("title", ""),
            "url": matched.get("url", ""),
            "one_liner": one_liner.strip(),
        })
    return cleaned


def _clean_single_pick(value: Any, pool: List[Dict[str, Any]], reason_field: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    reason = value.get(reason_field)
    if not isinstance(reason, str) or not reason.strip():
        return {}
    matched = _find_by_title(value.get("title"), pool)
    if not matched:
        return {}
    return {
        "title": matched.get("title", ""),
        "url": matched.get("url", ""),
        reason_field: reason.strip(),
    }


def _normalize_core_package(
    generated: Dict[str, Any],
    top_items: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Keep valid core fields and fill malformed/missing ones with the fallback."""
    fallback = _fallback_core_package(top_items)
    normalized = dict(fallback)
    usable_fields = 0

    tldr = _clean_string_list(generated.get("tldr"))[:5]
    if tldr:
        normalized["tldr"] = tldr
        usable_fields += 1

    paper_feature = _clean_feature(generated.get("paper_of_week"), PAPER_FEATURE_FIELDS)
    if paper_feature:
        normalized["paper_of_week"] = paper_feature
        usable_fields += 1

    tool_feature = _clean_feature(generated.get("tool_of_week"), TOOL_FEATURE_FIELDS)
    if tool_feature:
        normalized["tool_of_week"] = tool_feature
        usable_fields += 1

    if usable_fields == 0:
        raise ValueError("Core editorial response contains no usable fields")
    return normalized


def _normalize_extras_package(
    generated: Dict[str, Any],
    leftovers: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    pool = _leftover_pool_flat(leftovers)
    normalized = _fallback_extras_package()

    normalized["research_radar"] = _clean_radar_list(generated.get("research_radar"), pool)
    normalized["emerging_patterns"] = _clean_radar_list(generated.get("emerging_patterns"), pool)
    normalized["production_playbook"] = _clean_single_pick(
        generated.get("production_playbook"), pool, "summary"
    )
    normalized["under_the_radar"] = _clean_single_pick(
        generated.get("under_the_radar"), pool, "reason"
    )
    normalized["quick_hits"] = _clean_string_list(generated.get("quick_hits"))[:5]
    normalized["trending_topics"] = _clean_string_list(generated.get("trending_topics"))[:8]
    normalized["glossary"] = _clean_glossary(generated.get("glossary"))[:5]
    normalized["learning_paths"] = _clean_string_list(generated.get("learning_paths"))[:3]
    return normalized


def _source_anchored_features(
    core: Dict[str, Any],
    top_items: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Attach trusted titles and URLs rather than accepting LLM-generated links."""
    paper = top_items["top_papers"][0] if top_items["top_papers"] else {}
    tools = top_items["top_frameworks"] + top_items["top_github"]
    tool = tools[0] if tools else {}

    paper_feature = dict(core.get("paper_of_week") or {})
    tool_feature = dict(core.get("tool_of_week") or {})

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


@observe(name="create_editorial", as_type="agent")
def create_editorial(state: Dict[str, Any]) -> Dict[str, Any]:
    print("[Editor] Using deterministic ranking for top items...")
    top_items = _select_top_items(state)
    leftovers = _collect_leftovers(state)
    editorial_feedback = state.get("editorial_feedback")

    print("[Editor] Generating core editorial content (TL;DR, Paper/Tool of the Week)...")
    try:
        core_generated = _call(
            _build_core_prompt(top_items, editorial_feedback), max_tokens=900
        )
        if not isinstance(core_generated, dict):
            raise ValueError("Core editorial response must be a JSON object")
        core = _normalize_core_package(core_generated, top_items)
    except GroqRateLimitError as error:
        wait = error.retry_after_seconds
        retry_hint = f" Retry after approximately {wait:.0f} seconds." if wait else ""
        print(f"[Editor] Groq rate limit stopped editorial generation.{retry_hint}")
        raise
    except Exception as error:
        print(f"[Editor] Core editorial call failed: {error}")
        core = _fallback_core_package(top_items)

    print("[Editor] Generating best-effort extras (Research Radar, Quick Hits, ...)...")
    try:
        extras_generated = _call(_build_extras_prompt(leftovers), max_tokens=1200)
        if not isinstance(extras_generated, dict):
            raise ValueError("Extras editorial response must be a JSON object")
        extras = _normalize_extras_package(extras_generated, leftovers)
    except GroqRateLimitError as error:
        wait = error.retry_after_seconds
        retry_hint = f" Retry after approximately {wait:.0f} seconds." if wait else ""
        print(f"[Editor] Groq rate limit stopped extras generation.{retry_hint}")
        raise
    except Exception as error:
        print(f"[Editor] Extras editorial call failed: {error}")
        extras = _fallback_extras_package()

    anchored = _source_anchored_features(core, top_items)

    return {
        **top_items,
        "tldr": core["tldr"],
        **anchored,
        **extras,
    }
