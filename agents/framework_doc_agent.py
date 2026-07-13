"""Monitors specific AI framework repos for new releases and doc updates."""

import os
from github import Github
from datetime import datetime, timedelta
from typing import List, Dict, Any
import yaml

_FRAMEWORKS = [
    {"repo": "langchain-ai/langchain",   "name": "LangChain",  "docs": "https://python.langchain.com"},
    {"repo": "langchain-ai/langgraph",   "name": "LangGraph",  "docs": "https://langchain-ai.github.io/langgraph/"},
    {"repo": "crewAIInc/crewAI",         "name": "CrewAI",     "docs": "https://docs.crewai.com"},
    {"repo": "microsoft/autogen",         "name": "AutoGen",    "docs": "https://microsoft.github.io/autogen/"},
    {"repo": "run-llama/llama_index",    "name": "LlamaIndex", "docs": "https://docs.llamaindex.ai"},
    {"repo": "deepset-ai/haystack",      "name": "Haystack",   "docs": "https://docs.haystack.deepset.ai"},
    {"repo": "BerriAI/litellm",          "name": "LiteLLM",    "docs": "https://docs.litellm.ai"},
    {"repo": "vllm-project/vllm",        "name": "vLLM",       "docs": "https://docs.vllm.ai"},
    {"repo": "ollama/ollama",            "name": "Ollama",     "docs": "https://ollama.com/docs"},
    {"repo": "NVIDIA/NeMo",              "name": "NVIDIA NeMo","docs": "https://docs.nvidia.com/nemo-framework/"},
    {"repo": "unslothai/unsloth",        "name": "Unsloth",    "docs": "https://docs.unsloth.ai"},
    {"repo": "ggerganov/llama.cpp",      "name": "llama.cpp",  "docs": "https://github.com/ggerganov/llama.cpp"},
]


def _search_emerging_tools(g, days_back: int = 14) -> List[Dict[str, Any]]:
    """Search GitHub for new AI tools not in the fixed watch list."""
    watched = {fw["repo"].lower() for fw in _FRAMEWORKS}
    cutoff = datetime.now() - timedelta(days=days_back)
    emerging = []

    try:
        results = g.search_repositories(
            query=f"topic:llm created:>{cutoff.strftime('%Y-%m-%d')} stars:>50",
            sort="stars",
            order="desc",
        )
        for repo in results[:8]:
            if repo.full_name.lower() in watched:
                continue
            emerging.append({
                "title": repo.name,
                "framework": repo.name,
                "version": "New",
                "changelog": (repo.description or "")[:600],
                "url": repo.html_url,
                "docs_url": repo.homepage or repo.html_url,
                "repo": repo.full_name,
                "published": repo.created_at.strftime("%Y-%m-%d"),
                "stars": repo.stargazers_count,
                "source": "github_emerging",
                "type": "framework_update",
                "is_emerging": True,
            })
            if len(emerging) >= 3:
                break
    except Exception as e:
        print(f"[FrameworkAgent] Emerging tools search error: {e}")

    return emerging


def fetch_framework_updates(days_back: int = 7) -> List[Dict[str, Any]]:
    token = os.getenv("GITHUB_TOKEN", "")
    g = Github(token) if token else Github()
    cutoff = datetime.now() - timedelta(days=days_back)
    updates = []

    for fw in _FRAMEWORKS:
        try:
            repo = g.get_repo(fw["repo"])
            latest = repo.get_latest_release()
            pub = latest.published_at

            if pub and pub.replace(tzinfo=None) >= cutoff:
                changelog = (latest.body or "No changelog provided.")[:600].replace("\n", " ")
                updates.append({
                    "title": f"{fw['name']} {latest.tag_name} Released",
                    "framework": fw["name"],
                    "version": latest.tag_name,
                    "changelog": changelog,
                    "url": latest.html_url,
                    "docs_url": fw["docs"],
                    "repo": fw["repo"],
                    "published": pub.strftime("%Y-%m-%d"),
                    "stars": repo.stargazers_count,
                    "source": "framework_docs",
                    "type": "framework_update",
                    "is_emerging": False,
                })
        except Exception:
            pass

    # Add newly discovered AI tools from GitHub search
    updates += _search_emerging_tools(g, days_back=14)

    return updates
