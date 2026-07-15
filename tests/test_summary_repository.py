"""Tests for item-level PostgreSQL summary persistence."""

import unittest
from unittest.mock import MagicMock
from uuid import UUID

from database.summary_repository import SummaryRepository, canonicalize_url


class SummaryRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        self.repository = SummaryRepository(self.connection)

    def test_tracking_parameters_are_removed_from_source_url(self):
        self.assertEqual(
            canonicalize_url(
                "HTTPS://Example.com/story/?utm_source=test&version=2#section"
            ),
            "https://example.com/story?version=2",
        )

    def test_source_item_is_committed_immediately(self):
        source_id = UUID("12345678-1234-5678-1234-567812345678")
        self.cursor.fetchone.return_value = (source_id,)

        result = self.repository.upsert_source_item(
            item={"title": "Example", "url": "https://example.com/story"},
            item_type="news",
            content_hash="a" * 64,
            raw_content="Source content",
        )

        self.assertEqual(result, source_id)
        self.connection.commit.assert_called_once_with()
        self.assertIn("INSERT INTO source_items", self.cursor.execute.call_args.args[0])

    def test_exact_cache_hit_returns_summary(self):
        source_id = UUID("12345678-1234-5678-1234-567812345678")
        summary_id = UUID("87654321-4321-8765-4321-876543218765")
        expected = {"summary": "Cached"}
        self.cursor.fetchone.return_value = (summary_id, expected)

        result = self.repository.get_cached_summary(
            source_item_id=source_id,
            content_hash="a" * 64,
            model_name="model",
            prompt_fingerprint="b" * 64,
        )

        self.assertEqual(result, expected)
        self.assertEqual(self.cursor.execute.call_count, 2)
        self.connection.commit.assert_called_once_with()

    def test_cache_miss_does_not_commit(self):
        self.cursor.fetchone.return_value = None

        result = self.repository.get_cached_summary(
            source_item_id=UUID("12345678-1234-5678-1234-567812345678"),
            content_hash="a" * 64,
            model_name="model",
            prompt_fingerprint="b" * 64,
        )

        self.assertIsNone(result)
        self.connection.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
