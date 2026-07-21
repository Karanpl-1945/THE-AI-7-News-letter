"""Uses Groq to enrich each collected item with summary, difficulty, and insights."""

import hashlib
import json
import os
import re
from typing import List, Dict, Any

from langfuse import observe

from database.summary_repository import summary_repository
from llm.groq_client import GroqRateLimitError, get_groq_gateway


SUMMARY_PROMPT_VERSION = "summary-v1"
SUMMARY_MAX_TOKENS = 512
SUMMARY_FIELDS = (
    "summary",
    "why_it_matters",
    "key_takeaway",
    "difficulty",
    "tags",
)


def _raw_content(item: Dict[str, Any]) -> str:
    return str(
        item.get("abstract")
        or item.get("summary")
        or item.get("description")
        or item.get("changelog")
        or ""
    )


def _build_prompt(item: Dict[str, Any], item_type: str) -> str:
    raw_text = _raw_content(item)
    title = str(item.get("title", ""))
    interests = os.getenv("USER_INTERESTS", "LLMs,agents,computer vision")
    skill_level = os.getenv("SKILL_LEVEL", "intermediate")

    type_hints = {
        "paper":     "a research paper",
        "model":     "an AI model release or announcement",
        "github":    "a GitHub repository",
        "news":      "an AI news article",
        "framework": "a framework/library release",
    }
    context = type_hints.get(item_type, "an AI-related item")

    return f"""You are an expert AI journalist. Analyse this {context} and return ONLY valid JSON.

Reader interests: {interests}
Reader skill level: {skill_level}
Title: {title}
Content: {raw_text[:800]}

Return this exact JSON (no markdown, no extra text):
{{
  "summary": "3-4 sentence clear explanation of what this is and what it does",
  "why_it_matters": "1-2 sentences on real-world impact for an AI/ML practitioner",
  "key_takeaway": "One sentence — the single most important thing to know",
  "difficulty": "Beginner or Intermediate or Advanced",
  "tags": ["tag1", "tag2", "tag3"]
}}"""


def _request_fingerprints(
    item: Dict[str, Any],
    item_type: str,
    prompt: str,
) -> tuple[str, str]:
    content_payload = {
        "item_type": item_type,
        "title": str(item.get("title", "")),
        "content": _raw_content(item),
    }
    content_hash = hashlib.sha256(
        json.dumps(content_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    prompt_payload = {
        "version": SUMMARY_PROMPT_VERSION,
        "prompt": prompt,
        "max_tokens": SUMMARY_MAX_TOKENS,
    }
    prompt_fingerprint = hashlib.sha256(
        json.dumps(prompt_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return content_hash, prompt_fingerprint


def _validate_summary(data: Dict[str, Any]) -> None:
    """Reject incomplete Groq results so invalid output is never cached."""
    if not all(field in data for field in SUMMARY_FIELDS):
        raise ValueError("Groq summary response is missing required fields")
    if data["difficulty"] not in {"Beginner", "Intermediate", "Advanced"}:
        raise ValueError("Groq summary response has an invalid difficulty")
    if not isinstance(data["tags"], list):
        raise ValueError("Groq summary response tags must be a list")


def _strip_markdown(text: str) -> str:
    """Remove Markdown syntax so a raw changelog reads as prose, not source."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _truncate_at_boundary(text: str, limit: int) -> str:
    """Cut at a sentence or word boundary instead of mid-word/mid-sentence."""
    if len(text) <= limit:
        return text

    truncated = text[:limit]
    for separator in (". ", "! ", "? "):
        index = truncated.rfind(separator)
        if index > limit * 0.4:
            return truncated[: index + 1].strip()

    index = truncated.rfind(" ")
    if index > 0:
        return truncated[:index].strip() + "…"
    return truncated.strip() + "…"


def _fallback_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = _strip_markdown(_raw_content(item))
    return {
        **item,
        "summary": _truncate_at_boundary(cleaned, 300),
        "why_it_matters": "",
        "key_takeaway": "",
        "difficulty": "Intermediate",
        "tags": [],
    }


@observe(name="summarize_item", as_type="chain")
def _summarize_item(
    item: Dict[str, Any],
    item_type: str,
    allow_fallback: bool = True,
) -> Dict[str, Any]:
    title = item.get("title", "")
    prompt = _build_prompt(item, item_type)

    try:
        data = get_groq_gateway().create_json_completion(
            prompt=prompt,
            model=os.getenv("GROQ_SUMMARY_MODEL", "llama-3.1-8b-instant"),
            max_tokens=SUMMARY_MAX_TOKENS,
        )
        _validate_summary(data)
        return {**item, **data}
    except GroqRateLimitError as error:
        wait = error.retry_after_seconds
        retry_hint = f" Retry after approximately {wait:.0f} seconds." if wait else ""
        print(f"[Summarizer] Groq rate limit stopped summarization.{retry_hint}")
        raise
    except Exception as error:
        print(f"[Summarizer] Failed on '{title}': {error}")
        if not allow_fallback:
            raise
        return _fallback_summary(item)


@observe(name="summarize_items", as_type="chain")
def summarize_items(items: List[Dict[str, Any]], item_type: str) -> List[Dict[str, Any]]:
    if not items:
        return []

    model_name = os.getenv("GROQ_SUMMARY_MODEL", "llama-3.1-8b-instant")
    summarized: List[Dict[str, Any]] = []

    with summary_repository() as repository:
        for item in items:
            prompt = _build_prompt(item, item_type)
            content_hash, prompt_fingerprint = _request_fingerprints(
                item,
                item_type,
                prompt,
            )
            source_item_id = repository.upsert_source_item(
                item=item,
                item_type=item_type,
                content_hash=content_hash,
                raw_content=_raw_content(item),
            )
            cached = repository.get_cached_summary(
                source_item_id=source_item_id,
                content_hash=content_hash,
                model_name=model_name,
                prompt_fingerprint=prompt_fingerprint,
            )
            if cached is not None:
                print(f"[Summarizer] Cache hit: {item.get('title', '')}")
                summarized.append({**item, **cached})
                continue

            try:
                enriched = _summarize_item(
                    item,
                    item_type,
                    allow_fallback=False,
                )
            except GroqRateLimitError:
                raise
            except Exception:
                summarized.append(_fallback_summary(item))
                continue

            summary_data = {
                field: enriched[field]
                for field in SUMMARY_FIELDS
            }
            repository.save_summary(
                source_item_id=source_item_id,
                content_hash=content_hash,
                model_name=model_name,
                prompt_version=SUMMARY_PROMPT_VERSION,
                prompt_fingerprint=prompt_fingerprint,
                summary=summary_data,
            )
            summarized.append(enriched)

    return summarized
