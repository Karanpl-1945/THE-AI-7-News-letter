import os
import unittest
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from agents.summarizer import (
    _fallback_summary,
    _strip_markdown,
    _summarize_item,
    _truncate_at_boundary,
    summarize_items,
)
from llm.groq_client import GroqQuotaExhaustedError


class FallbackSummaryTextTests(unittest.TestCase):
    def test_strip_markdown_removes_headers_code_and_links(self):
        raw = (
            "## Verify Docker Image Signature\n\n"
            "All images are signed with [cosign](https://docs.sigstore.dev). "
            "Run `cosign verify` first.\n\n"
            "```bash\ncosign verify --key cosign.pub image:tag\n```\n\n"
            "This confirms the release is authentic."
        )

        cleaned = _strip_markdown(raw)

        self.assertNotIn("##", cleaned)
        self.assertNotIn("```", cleaned)
        self.assertNotIn("[cosign]", cleaned)
        self.assertNotIn("cosign verify --key", cleaned)
        self.assertIn("cosign verify", cleaned)
        self.assertIn("This confirms the release is authentic.", cleaned)

    def test_truncate_at_boundary_cuts_on_a_sentence_not_mid_word(self):
        text = "First sentence is here. Second sentence goes on for a while longer than the limit."

        truncated = _truncate_at_boundary(text, 30)

        self.assertEqual(truncated, "First sentence is here.")

    def test_truncate_at_boundary_falls_back_to_word_boundary(self):
        text = ("onelongwordthatkeepsgoing " * 5).strip()

        truncated = _truncate_at_boundary(text, 20)

        self.assertTrue(truncated.endswith("…"))

    def test_fallback_summary_never_leaks_raw_markdown(self):
        item = {
            "title": "some/repo — v1.0.0",
            "changelog": "## What's Changed\n\n- Fixed a bug in `parser.py` (#123)\n\n"
            "```python\nraise ValueError('bad')\n```",
        }

        result = _fallback_summary(item)

        self.assertNotIn("##", result["summary"])
        self.assertNotIn("```", result["summary"])


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
        repository = Mock()
        repository.upsert_source_item.side_effect = [uuid4(), uuid4()]
        repository.get_cached_summary.return_value = None
        repository_context = MagicMock()
        repository_context.__enter__.return_value = repository

        with patch("agents.summarizer.get_groq_gateway", return_value=gateway):
            with patch(
                "agents.summarizer.summary_repository",
                return_value=repository_context,
            ):
                with patch.dict(os.environ, {"GROQ_SUMMARY_MODEL": "summary-test-model"}):
                    result = summarize_items(items, "paper")

        self.assertEqual([item["summary"] for item in result], ["First summary", "Second summary"])
        self.assertEqual(gateway.create_json_completion.call_count, 2)
        for call in gateway.create_json_completion.call_args_list:
            self.assertEqual(call.kwargs["model"], "summary-test-model")
            self.assertEqual(call.kwargs["max_tokens"], 512)
        self.assertEqual(repository.save_summary.call_count, 2)

    def test_cache_hit_skips_groq(self):
        gateway = Mock()
        item = {"title": "Cached", "summary": "Source", "url": "https://example.com"}
        cached = {
            "summary": "Stored summary",
            "why_it_matters": "Stored impact",
            "key_takeaway": "Stored takeaway",
            "difficulty": "Beginner",
            "tags": ["cached"],
        }
        repository = Mock()
        repository.upsert_source_item.return_value = uuid4()
        repository.get_cached_summary.return_value = cached
        repository_context = MagicMock()
        repository_context.__enter__.return_value = repository

        with patch("agents.summarizer.get_groq_gateway", return_value=gateway):
            with patch(
                "agents.summarizer.summary_repository",
                return_value=repository_context,
            ):
                result = summarize_items([item], "news")

        self.assertEqual(result[0]["summary"], "Stored summary")
        gateway.create_json_completion.assert_not_called()
        repository.save_summary.assert_not_called()

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

    def test_retry_reuses_items_saved_before_rate_limit(self):
        first_summary = {
            "summary": "First summary",
            "why_it_matters": "First impact",
            "key_takeaway": "First takeaway",
            "difficulty": "Beginner",
            "tags": ["first"],
        }
        second_summary = {
            "summary": "Second summary",
            "why_it_matters": "Second impact",
            "key_takeaway": "Second takeaway",
            "difficulty": "Intermediate",
            "tags": ["second"],
        }
        rate_limit = GroqQuotaExhaustedError(
            "daily quota exhausted",
            retry_after_seconds=600,
        )
        gateway = Mock()
        gateway.create_json_completion.side_effect = [
            first_summary,
            rate_limit,
            second_summary,
        ]
        items = [
            {"title": "First", "summary": "First source", "url": "https://example.com/1"},
            {"title": "Second", "summary": "Second source", "url": "https://example.com/2"},
        ]

        first_repository = Mock()
        first_repository.upsert_source_item.side_effect = [uuid4(), uuid4()]
        first_repository.get_cached_summary.return_value = None
        second_repository = Mock()
        second_repository.upsert_source_item.side_effect = [uuid4(), uuid4()]
        second_repository.get_cached_summary.side_effect = [first_summary, None]
        repository_context = MagicMock()
        repository_context.__enter__.side_effect = [
            first_repository,
            second_repository,
        ]

        with patch("agents.summarizer.get_groq_gateway", return_value=gateway):
            with patch(
                "agents.summarizer.summary_repository",
                return_value=repository_context,
            ):
                with self.assertRaises(GroqQuotaExhaustedError):
                    summarize_items(items, "news")
                result = summarize_items(items, "news")

        self.assertEqual(first_repository.save_summary.call_count, 1)
        self.assertEqual(result[0]["summary"], "First summary")
        self.assertEqual(result[1]["summary"], "Second summary")
        self.assertEqual(gateway.create_json_completion.call_count, 3)


if __name__ == "__main__":
    unittest.main()
