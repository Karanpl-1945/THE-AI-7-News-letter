"""Groq-powered editor: curates top stories, writes headlines, and creates special features."""

import os
import json
from typing import Dict, Any, List
from groq import Groq
from langfuse import observe

_client = None

def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client

@observe(name="groq_editor_call", as_type="chain")
def _call(prompt: str, max_tokens: int = 1024) -> str:
    resp = _get_client().chat.completions.create(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return (resp.choices[0].message.content or "{}").strip()


@observe(name="select_top_items", as_type="chain")
def _select_top_items(state: Dict) -> Dict[str, List]:
    """Pick top items per category."""
    def fmt(items, limit=5):
        return "\n".join(f"- {i.get('title','')}: {i.get('summary','')[:150]}" for i in items[:limit*2])

    prompt = f"""You are the editor of an AI/ML weekly newspaper. Select the BEST items from each category.
User interests: {os.getenv('USER_INTERESTS', 'LLMs, agents')}
Skill level: {os.getenv('SKILL_LEVEL', 'intermediate')}

PAPERS (pick top 5 by novelty/impact):
{fmt(state.get('summarized_papers', []))}

MODELS & RELEASES (pick top 3):
{fmt(state.get('summarized_models', []))}

GITHUB TRENDING (pick top 5):
{fmt(state.get('summarized_github', []))}

FRAMEWORK UPDATES (pick top 3):
{fmt(state.get('summarized_frameworks', []))}

NEWS (pick top 4):
{fmt(state.get('summarized_news', []))}

Return ONLY valid JSON:
{{
  "top_papers": [0,1,2,3,4],
  "top_models": [0,1,2],
  "top_github": [0,1,2,3,4],
  "top_frameworks": [0,1,2],
  "top_news": [0,1,2,3]
}}
(indices into each list above, 0-based)"""

    try:
        data = json.loads(_call(prompt, 512))
        return {
            "top_papers":     [state.get("summarized_papers", [])[i] for i in data.get("top_papers", [])[:5] if i < len(state.get("summarized_papers", []))],
            "top_models":     [state.get("summarized_models", [])[i] for i in data.get("top_models", [])[:3] if i < len(state.get("summarized_models", []))],
            "top_github":     [state.get("summarized_github", [])[i] for i in data.get("top_github", [])[:5] if i < len(state.get("summarized_github", []))],
            "top_frameworks": [state.get("summarized_frameworks", [])[i] for i in data.get("top_frameworks", [])[:3] if i < len(state.get("summarized_frameworks", []))],
            "top_news":       [state.get("summarized_news", [])[i] for i in data.get("top_news", [])[:4] if i < len(state.get("summarized_news", []))],
        }
    except Exception as e:
        print(f"[Editor] Selection failed: {e}")
        return {
            "top_papers":     state.get("summarized_papers", [])[:5],
            "top_models":     state.get("summarized_models", [])[:3],
            "top_github":     state.get("summarized_github", [])[:5],
            "top_frameworks": state.get("summarized_frameworks", [])[:3],
            "top_news":       state.get("summarized_news", [])[:4],
        }


@observe(name="write_tldr_and_pick", as_type="chain")
def _write_tldr_and_pick(top_items: Dict) -> Dict[str, Any]:
    category_labels = {
        "top_papers":     "Research Paper",
        "top_models":     "Model Release",
        "top_github":     "GitHub Trending",
        "top_frameworks": "Framework Update",
        "top_news":       "AI News",
    }

    categorized = []
    for key, items in top_items.items():
        label = category_labels.get(key, key)
        for item in items[:3]:
            categorized.append(f"[{label}] {item.get('title', '')}")

    prompt = f"""You are the editor of THE AI 7 weekly AI intelligence brief.
This week's top stories across all categories:
{json.dumps(categorized[:20])}

Write exactly 5 TL;DR bullets — each must cover a DIFFERENT category (one from Research Papers, one from Model Releases, one from GitHub, one from Frameworks, one from News). Do NOT write multiple bullets from the same category.

Return ONLY valid JSON:
{{
  "tldr": [
    "[Research Paper] one sentence summary",
    "[Model Release] one sentence summary",
    "[GitHub] one sentence summary",
    "[Framework] one sentence summary",
    "[News] one sentence summary"
  ],
  "editors_pick_title": "Title of the single most important story this week",
  "editors_pick_reason": "2-3 sentence explanation of why this is the most important story and what it means for the field"
}}"""

    try:
        return json.loads(_call(prompt, 600))
    except Exception as e:
        print(f"[Editor] TL;DR failed: {e}")
        return {"tldr": categorized[:5], "editors_pick_title": categorized[0] if categorized else "", "editors_pick_reason": ""}


@observe(name="write_paper_of_week", as_type="chain")
def _write_paper_of_week(papers: List[Dict]) -> Dict[str, Any]:
    if not papers:
        return {}
    paper = papers[0]

    prompt = f"""Write a detailed "Paper of the Week" breakdown for an AI/ML newspaper.
Paper: {paper.get('title')}
Abstract: {paper.get('abstract', '')[:600]}

Return ONLY valid JSON:
{{
  "title": "{paper.get('title')}",
  "url": "{paper.get('url', '')}",
  "problem": "What problem does this paper solve? (2 sentences)",
  "approach": "How does it solve it? (2-3 sentences, no jargon)",
  "results": "What are the key results/benchmarks? (1-2 sentences)",
  "implications": "What does this mean for the field? (2 sentences)",
  "why_you_should_care": "Why should an AI practitioner read this? (1 sentence)",
  "difficulty": "{paper.get('difficulty', 'Advanced')}"
}}"""

    try:
        return json.loads(_call(prompt, 700))
    except Exception as e:
        print(f"[Editor] Paper of week failed: {e}")
        return paper


@observe(name="write_tool_of_week", as_type="chain")
def _write_tool_of_week(frameworks: List[Dict], github: List[Dict]) -> Dict[str, Any]:
    tools = frameworks + github
    if not tools:
        return {}
    tool = tools[0]

    prompt = f"""Write a "Tool of the Week" feature for an AI/ML newspaper.
Tool: {tool.get('title')}
Description: {tool.get('description') or tool.get('changelog') or tool.get('summary', '')}
URL: {tool.get('url', '')}
Docs: {tool.get('docs_url', tool.get('url', ''))}

Return ONLY valid JSON:
{{
  "name": "Tool name",
  "url": "{tool.get('url', '')}",
  "docs_url": "{tool.get('docs_url', tool.get('url', ''))}",
  "what_it_is": "What is this tool and what problem does it solve? (2 sentences)",
  "whats_new": "What changed in this version / why is it trending? (2 sentences)",
  "comparison": "How is this version better than before? What specifically improved — speed, accuracy, API, features? (2-3 sentences comparing old vs new)",
  "install_cmd": "pip install command (one line)",
  "quickstart_code": "A minimal working Python code snippet (5-10 lines) to try this tool. Use proper Python syntax.",
  "who_should_use": "What kind of developer/researcher would benefit most? (1 sentence)"
}}"""

    try:
        return json.loads(_call(prompt, 900))
    except Exception as e:
        print(f"[Editor] Tool of week failed: {e}")
        return {"name": tool.get("title", ""), "url": tool.get("url", ""), "docs_url": "", "what_it_is": tool.get("summary", ""), "whats_new": "", "comparison": "", "install_cmd": "", "quickstart_code": "", "who_should_use": ""}


@observe(name="write_glossary_and_paths", as_type="chain")
def _write_glossary_and_paths(all_items: List[Dict]) -> Dict[str, Any]:
    titles_and_tags = []
    for item in all_items[:20]:
        titles_and_tags.append(item.get("title", ""))
        titles_and_tags.extend(item.get("tags", []))

    prompt = f"""Based on this week's AI/ML topics: {json.dumps(list(set(titles_and_tags))[:25])}
User skill level: {os.getenv('SKILL_LEVEL', 'intermediate')}

Return ONLY valid JSON:
{{
  "glossary": [
    {{"term": "Term 1", "definition": "Simple 1-sentence definition"}},
    {{"term": "Term 2", "definition": "Simple 1-sentence definition"}},
    {{"term": "Term 3", "definition": "Simple 1-sentence definition"}},
    {{"term": "Term 4", "definition": "Simple 1-sentence definition"}},
    {{"term": "Term 5", "definition": "Simple 1-sentence definition"}}
  ],
  "learning_paths": [
    "Path 1: To understand [topic], start with [resource] then [resource]",
    "Path 2: ...",
    "Path 3: ..."
  ],
  "trending_topics": ["topic1","topic2","topic3","topic4","topic5","topic6","topic7","topic8"]
}}"""

    try:
        return json.loads(_call(prompt, 800))
    except Exception as e:
        print(f"[Editor] Glossary failed: {e}")
        return {"glossary": [], "learning_paths": [], "trending_topics": []}


@observe(name="create_editorial", as_type="agent")
def create_editorial(state: Dict) -> Dict[str, Any]:
    print("[Editor] Selecting top items...")
    top_items = _select_top_items(state)

    print("[Editor] Writing TL;DR and Editor's Pick...")
    tldr_data = _write_tldr_and_pick(top_items)

    print("[Editor] Writing Paper of the Week...")
    paper_of_week = _write_paper_of_week(top_items.get("top_papers", []))

    print("[Editor] Writing Tool of the Week...")
    tool_of_week = _write_tool_of_week(
        top_items.get("top_frameworks", []),
        top_items.get("top_github", []),
    )

    all_items = sum(top_items.values(), [])
    print("[Editor] Writing Glossary and Learning Paths...")
    meta = _write_glossary_and_paths(all_items)

    # Papers that didn't make top 5 — shown as "More Research Papers"
    top_paper_titles = {p.get("title", "") for p in top_items.get("top_papers", [])}
    more_papers = [
        p for p in state.get("summarized_papers", [])
        if p.get("title", "") not in top_paper_titles
    ][:4]

    return {
        **top_items,
        "tldr": tldr_data.get("tldr", []),
        "editors_pick_title": tldr_data.get("editors_pick_title", ""),
        "editors_pick_reason": tldr_data.get("editors_pick_reason", ""),
        "paper_of_week": paper_of_week,
        "tool_of_week": tool_of_week,
        "glossary": meta.get("glossary", []),
        "learning_paths": meta.get("learning_paths", []),
        "trending_topics": meta.get("trending_topics", []),
        "more_papers": more_papers,
    }
