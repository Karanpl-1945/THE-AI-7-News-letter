"""Aggregates AI news from RSS feeds and Reddit communities."""

import feedparser
import yaml, os
from datetime import datetime, timedelta
from typing import List, Dict, Any


def _load_config() -> Dict:
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "sources.yaml")
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def _parse_feed(feed_info: Dict, cutoff: datetime, max_items: int = 5) -> List[Dict[str, Any]]:
    items = []
    try:
        feed = feedparser.parse(feed_info["url"])
        for entry in feed.entries[:max_items * 2]:
            pub = entry.get("published_parsed") or entry.get("updated_parsed")
            if pub:
                pub_dt = datetime(*pub[:6])
                if pub_dt < cutoff:
                    continue
            else:
                pub_dt = datetime.now()

            title = entry.get("title", "").strip()
            summary = (entry.get("summary") or entry.get("content", [{}])[0].get("value", ""))
            summary = summary[:500].replace("\n", " ").strip()

            if not title:
                continue

            items.append({
                "title": title,
                "summary": summary,
                "url": entry.get("link", ""),
                "published": pub_dt.strftime("%Y-%m-%d"),
                "source": feed_info["name"],
                "type": "news",
            })
            if len(items) >= max_items:
                break
    except Exception as e:
        print(f"[NewsAgent] Error fetching {feed_info['name']}: {e}")
    return items


def fetch_news(days_back: int = 7) -> List[Dict[str, Any]]:
    cfg = _load_config()["rss_feeds"]
    cutoff = datetime.now() - timedelta(days=days_back)

    all_items = []
    all_feeds = cfg.get("ai_blogs", []) + cfg.get("community", [])

    for feed_info in all_feeds:
        all_items.extend(_parse_feed(feed_info, cutoff))

    # Sort by date descending
    all_items.sort(key=lambda x: x["published"], reverse=True)
    return all_items
