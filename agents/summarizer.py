"""Uses Groq to enrich each collected item with summary, difficulty, and insights."""

import os
import json
from typing import List, Dict, Any
from groq import Groq
from langfuse import observe

_client = None

def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


@observe(name="summarize_item", as_type="chain")
def _summarize_item(item: Dict[str, Any], item_type: str) -> Dict[str, Any]:
    raw_text = item.get("abstract") or item.get("summary") or item.get("description") or item.get("changelog") or ""
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
        resp = _get_client().chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},  # Groq supports JSON mode on most models
        )
        data = json.loads(resp.choices[0].message.content.strip())
        return {**item, **data}
    except Exception as e:
        print(f"[Summarizer] Failed on '{title}': {e}")
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
