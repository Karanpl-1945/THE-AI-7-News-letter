import os
import unittest
from unittest.mock import Mock, patch

from agents.summarizer import _summarize_item, summarize_items
from llm.groq_client import GroqQuotaExhaustedError


class SummarizerTests(unittest.TestCase):
    def test_summarize_items_uses_shared_gateway_and_summary_model(self):
        gateway = Mock()
        gateway.create_json_completion.side_effect = [
            {
                "summary": "First summary",
                "why_it_matters": "First impact",
                "key_takeaway": "First takeaway",
                "difficulty": "Beginner",
                "tags": ["one"],
            },
            {
                "summary": "Second summary",
                "why_it_matters": "Second impact",
                "key_takeaway": "Second takeaway",
                "difficulty": "Advanced",
                "tags": ["two"],
            },
        ]
        items = [
            {"title": "First", "abstract": "First abstract"},
            {"title": "Second", "abstract": "Second abstract"},
        ]

        with patch("agents.summarizer.get_groq_gateway", return_value=gateway):
            with patch.dict(os.environ, {"GROQ_SUMMARY_MODEL": "summary-test-model"}):
                result = summarize_items(items, "paper")

        self.assertEqual([item["summary"] for item in result], ["First summary", "Second summary"])
        self.assertEqual(gateway.create_json_completion.call_count, 2)
        for call in gateway.create_json_completion.call_args_list:
            self.assertEqual(call.kwargs["model"], "summary-test-model")
            self.assertEqual(call.kwargs["max_tokens"], 512)

    def test_non_rate_error_keeps_item_level_fallback(self):
        gateway = Mock()
        gateway.create_json_completion.side_effect = ValueError("invalid JSON")
        item = {"title": "Fallback", "abstract": "Original abstract text"}

        with patch("agents.summarizer.get_groq_gateway", return_value=gateway):
            result = _summarize_item(item, "paper")

        self.assertEqual(result["summary"], "Original abstract text")
        self.assertEqual(result["difficulty"], "Intermediate")
        self.assertEqual(result["tags"], [])

    def test_daily_quota_error_propagates_and_stops_summarization(self):
        gateway = Mock()
        gateway.create_json_completion.side_effect = GroqQuotaExhaustedError(
            "daily quota exhausted",
            retry_after_seconds=600,
        )

        with patch("agents.summarizer.get_groq_gateway", return_value=gateway):
            with self.assertRaises(GroqQuotaExhaustedError):
                _summarize_item({"title": "Quota", "summary": "Source"}, "news")


if __name__ == "__main__":
    unittest.main()
