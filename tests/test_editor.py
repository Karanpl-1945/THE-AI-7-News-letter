import unittest
from unittest.mock import patch

from agents.editor import create_editorial
from llm.groq_client import GroqQuotaExhaustedError


def _items(prefix: str, count: int):
    return [
        {
            "title": f"{prefix} {index}",
            "summary": f"Summary for {prefix} {index}",
            "why_it_matters": f"Why {prefix} {index} matters",
            "key_takeaway": f"Takeaway for {prefix} {index}",
            "url": f"https://example.com/{prefix.lower()}/{index}",
            "docs_url": f"https://docs.example.com/{prefix.lower()}/{index}",
            "difficulty": "Intermediate",
            "tags": [prefix.lower(), "ai"],
        }
        for index in range(count)
    ]


def _state():
    return {
        "summarized_papers": _items("Paper", 7),
        "summarized_models": _items("Model", 4),
        "summarized_github": _items("GitHub", 7),
        "summarized_frameworks": _items("Framework", 4),
        "summarized_news": _items("News", 5),
    }


class EditorTests(unittest.TestCase):
    def test_editor_uses_one_call_and_preserves_output_contract(self):
        generated = {
            "tldr": [f"Bullet {index}" for index in range(5)],
            "editors_pick_title": "Paper 0",
            "editors_pick_reason": "It matters.",
            "paper_of_week": {
                "problem": "Problem",
                "approach": "Approach",
                "results": "Results",
                "implications": "Implications",
                "why_you_should_care": "Reason",
            },
            "tool_of_week": {
                "what_it_is": "Tool description",
                "whats_new": "New behavior",
                "comparison": "Comparison",
                "install_cmd": "pip install example",
                "quickstart_code": "import example",
                "who_should_use": "Developers",
            },
            "glossary": [{"term": "Agent", "definition": "A system."}],
            "learning_paths": ["Read the guide"],
            "trending_topics": ["agents"],
        }

        with patch("agents.editor._call", return_value=generated) as groq_call:
            result = create_editorial(_state())

        groq_call.assert_called_once()
        self.assertEqual(groq_call.call_args.kwargs["max_tokens"], 1800)
        self.assertIn("Produce the complete editorial package in ONE response", groq_call.call_args.args[0])
        self.assertEqual(len(result["top_papers"]), 5)
        self.assertEqual(len(result["top_models"]), 3)
        self.assertEqual(len(result["top_github"]), 5)
        self.assertEqual(len(result["top_frameworks"]), 3)
        self.assertEqual(len(result["top_news"]), 4)
        self.assertEqual(result["paper_of_week"]["title"], "Paper 0")
        self.assertEqual(result["paper_of_week"]["url"], "https://example.com/paper/0")
        self.assertEqual(result["tool_of_week"]["name"], "Framework 0")
        self.assertEqual(result["tool_of_week"]["url"], "https://example.com/framework/0")
        self.assertEqual([paper["title"] for paper in result["more_papers"]], ["Paper 5", "Paper 6"])

    def test_editor_returns_deterministic_fallback_after_one_failed_call(self):
        with patch("agents.editor._call", side_effect=RuntimeError("quota exhausted")) as groq_call:
            result = create_editorial(_state())

        groq_call.assert_called_once()
        self.assertEqual(result["editors_pick_title"], "Paper 0")
        self.assertEqual(len(result["tldr"]), 5)
        self.assertEqual(result["paper_of_week"]["title"], "Paper 0")
        self.assertEqual(result["tool_of_week"]["name"], "Framework 0")
        self.assertEqual(result["glossary"], [])
        self.assertEqual(result["learning_paths"], [])
        self.assertEqual(result["trending_topics"], [])

    def test_partial_editorial_normalizes_invalid_and_missing_fields(self):
        generated = {
            "tldr": ["Valid bullet", 123, ""],
            "editors_pick_title": ["not a string"],
            "paper_of_week": "not an object",
            "tool_of_week": {"what_it_is": "Valid tool", "comparison": 42},
            "glossary": [
                {"term": "Agent", "definition": "A system."},
                {"term": "Broken"},
            ],
        }

        with patch("agents.editor._call", return_value=generated) as groq_call:
            result = create_editorial(_state())

        groq_call.assert_called_once()
        self.assertEqual(result["tldr"], ["Valid bullet"])
        self.assertEqual(result["editors_pick_title"], "Paper 0")
        self.assertEqual(result["paper_of_week"]["title"], "Paper 0")
        self.assertEqual(result["tool_of_week"]["what_it_is"], "Valid tool")
        self.assertNotIn("comparison", result["tool_of_week"])
        self.assertEqual(
            result["glossary"],
            [{"term": "Agent", "definition": "A system."}],
        )

    def test_object_with_no_usable_fields_uses_deterministic_fallback(self):
        generated = {
            "tldr": "not a list",
            "editors_pick_title": [],
            "paper_of_week": None,
            "tool_of_week": 123,
            "glossary": [{"term": "Missing definition"}],
        }

        with patch("agents.editor._call", return_value=generated) as groq_call:
            result = create_editorial(_state())

        groq_call.assert_called_once()
        self.assertEqual(result["editors_pick_title"], "Paper 0")
        self.assertEqual(len(result["tldr"]), 5)
        self.assertEqual(result["glossary"], [])

    def test_editor_propagates_quota_error_instead_of_publishing_fallback(self):
        quota_error = GroqQuotaExhaustedError(
            "daily quota exhausted",
            retry_after_seconds=900,
        )
        with patch("agents.editor._call", side_effect=quota_error):
            with self.assertRaises(GroqQuotaExhaustedError):
                create_editorial(_state())


if __name__ == "__main__":
    unittest.main()
