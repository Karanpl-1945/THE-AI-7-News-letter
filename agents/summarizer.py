"""Uses Groq to enrich each collected item with summary, difficulty, and insights."""

import os
from typing import List, Dict, Any
from langfuse import observe
from llm.groq_client import GroqRateLimitError, get_groq_gateway


@observe(name="summarize_item", as_type="chain")
def _summarize_item(item: Dict[str, Any], item_type: str) -> Dict[str, Any]:
    raw_text = (
        item.get("abstract")
        or item.get("summary")
        or item.get("description")
        or item.get("changelog")
        or ""
    )
    title = item.get("title", "")

    type_hints = {
        "paper":     "a research paper",
        "model":     "an AI model release or announcement",
        "github":    "a GitHub repository",
        "news":      "an AI news article",
        "framework": "a framework/library release",
    }
    context = type_hints.get(item_type, "an AI-related item")

    prompt = f"""You are an expert AI journalist. Analyse this {context} and return ONLY valid JSON.

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

    try:
        data = get_groq_gateway().create_json_completion(
            prompt=prompt,
            model=os.getenv("GROQ_SUMMARY_MODEL", "llama-3.1-8b-instant"),
            max_tokens=512,
        )
        return {**item, **data}
    except GroqRateLimitError as error:
        wait = error.retry_after_seconds
        retry_hint = f" Retry after approximately {wait:.0f} seconds." if wait else ""
        print(f"[Summarizer] Groq rate limit stopped summarization.{retry_hint}")
        raise
    except Exception as error:
        print(f"[Summarizer] Failed on '{title}': {error}")
        return {
            **item,
            "summary": raw_text[:300],
            "why_it_matters": "",
            "key_takeaway": "",
            "difficulty": "Intermediate",
            "tags": [],
        }


@observe(name="summarize_items", as_type="chain")
def summarize_items(items: List[Dict[str, Any]], item_type: str) -> List[Dict[str, Any]]:
    return [_summarize_item(item, item_type) for item in items]
