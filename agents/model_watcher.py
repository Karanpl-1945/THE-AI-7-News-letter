"""Tracks new AI model releases from company blogs via RSS."""

import feedparser
import yaml, os
from datetime import datetime, timedelta
from typing import List, Dict, Any

_BLOG_FEEDS = [
    {"name": "OpenAI",     "url": "https://openai.com/blog/rss.xml"},
    {"name": "Anthropic",  "url": "https://www.anthropic.com/rss.xml"},
    {"name": "Google AI",  "url": "https://blog.google/technology/ai/rss/"},
    {"name": "Meta AI",    "url": "https://ai.meta.com/blog/rss.xml"},
    {"name": "HuggingFace","url": "https://huggingface.co/blog/feed.xml"},
    {"name": "Mistral",    "url": "https://mistral.ai/news/rss.xml"},
    {"name": "Cohere",     "url": "https://cohere.com/blog/rss.xml"},
]

_MODEL_KEYWORDS = [
    "model", "release", "launch", "gpt", "claude", "gemini", "llama",
    "mistral", "phi", "falcon", "benchmark", "multimodal", "weights",
    "open-source", "fine-tun",
]


def _is_model_related(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in _MODEL_KEYWORDS)


def fetch_model_news(days_back: int = 7) -> List[Dict[str, Any]]:
    cutoff = datetime.now() - timedelta(days=days_back)
    items = []

    for feed_info in _BLOG_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:15]:
                pub = entry.get("published_parsed") or entry.get("updated_parsed")
                if pub:
                    pub_dt = datetime(*pub[:6])
                    if pub_dt < cutoff:
                        continue
                else:
                    pub_dt = datetime.now()

                title = entry.get("title", "")
                summary = entry.get("summary", "")[:500]

                if not _is_model_related(title, summary):
                    continue

                items.append({
                    "title": title,
                    "summary": summary.replace("\n", " "),
                    "url": entry.get("link", ""),
                    "published": pub_dt.strftime("%Y-%m-%d"),
                    "source": feed_info["name"],
                    "type": "model_news",
                })
        except Exception as e:
            print(f"[ModelWatcher] Error fetching {feed_info['name']}: {e}")

    return items
