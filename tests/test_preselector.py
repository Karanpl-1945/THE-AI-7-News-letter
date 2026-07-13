"""Unit tests for deterministic pre-LLM filtering and ranking."""

import os
import unittest

from agents.preselector import preselect_for_summarization, select_items, selection_score


class PreselectorTests(unittest.TestCase):
    def test_select_items_obeys_limit_and_is_deterministic(self):
        items = [
            {
                "title": f"Story {number}",
                "published": f"2026-07-{number:02d}",
                "summary": "Useful content " * number,
                "source": "source-a",
            }
            for number in range(1, 11)
        ]

        first = select_items(items, limit=4)
        second = select_items(items, limit=4)

        self.assertEqual(len(first), 4)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["title"], "Story 10")
        self.assertIn("breakdown", first[0]["_selection"])

    def test_source_cap_increases_diversity(self):
        items = [
            {
                "title": f"A{number}",
                "published": "2026-07-12",
                "summary": "A" * (600 - number),
                "source": "source-a",
            }
            for number in range(4)
        ] + [
            {
                "title": f"B{number}",
                "published": "2026-07-11",
                "summary": "B" * 500,
                "source": "source-b",
            }
            for number in range(4)
        ]

        selected = select_items(items, limit=4, max_per_source=2)

        self.assertEqual(len(selected), 4)
        self.assertEqual({item["source"] for item in selected}, {"source-a", "source-b"})

    def test_user_interest_improves_relevance_score(self):
        previous = os.environ.get("USER_INTERESTS")
        os.environ["USER_INTERESTS"] = "agents"
        try:
            agent_story = {
                "title": "A new agentic tool-use framework",
                "published": "2026-07-12",
                "summary": "A framework for autonomous agents.",
                "url": "https://example.com/agents",
                "source": "MIT Technology Review AI",
            }
            unrelated_story = {
                **agent_story,
                "title": "A database storage update",
                "summary": "New database storage features.",
                "url": "https://example.com/database",
            }
            self.assertGreater(
                selection_score(agent_story, "news"),
                selection_score(unrelated_story, "news"),
            )
        finally:
            if previous is None:
                os.environ.pop("USER_INTERESTS", None)
            else:
                os.environ["USER_INTERESTS"] = previous

    def test_duplicate_url_with_tracking_parameters_is_removed(self):
        items = [
            {
                "title": "Original announcement",
                "published": "2026-07-12",
                "summary": "A" * 600,
                "url": "https://example.com/story?utm_source=rss",
                "source": "source-a",
            },
            {
                "title": "Syndicated announcement",
                "published": "2026-07-11",
                "summary": "B" * 600,
                "url": "https://example.com/story",
                "source": "source-b",
            },
        ]

        selected = select_items(items, limit=2, category="news")

        self.assertEqual(len(selected), 1)

    def test_configured_pipeline_budget_is_thirty_items(self):
        sample = {
            "papers": [{"title": str(i)} for i in range(20)],
            "model_news": [{"title": str(i)} for i in range(20)],
            "github_trends": [{"title": str(i)} for i in range(20)],
            "news_items": [{"title": str(i)} for i in range(20)],
            "framework_updates": [{"title": str(i)} for i in range(20)],
        }

        selected = preselect_for_summarization(sample)

        self.assertEqual(len(selected["selected_papers"]), 8)
        self.assertEqual(len(selected["selected_models"]), 4)
        self.assertEqual(len(selected["selected_github"]), 6)
        self.assertEqual(len(selected["selected_news"]), 8)
        self.assertEqual(len(selected["selected_frameworks"]), 4)
        self.assertEqual(sum(map(len, selected.values())), 30)


if __name__ == "__main__":
    unittest.main()
