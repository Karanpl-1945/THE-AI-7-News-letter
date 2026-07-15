"""Tests for the application schema migration command."""

import unittest
from unittest.mock import MagicMock, patch

from database.migrate import MIGRATIONS, apply_application_schema


class DatabaseMigrationTests(unittest.TestCase):
    def test_summary_cache_migration_defines_only_approved_tables(self):
        sql = MIGRATIONS[0].read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS source_items", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS article_summaries", sql)
        self.assertIn("uq_article_summary_cache", sql)

    @patch("database.migrate.database_connection")
    def test_application_schema_executes_migration(self, mock_connection):
        connection = MagicMock()
        cursor = MagicMock()
        mock_connection.return_value.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = cursor

        apply_application_schema("postgresql://user:secret@db/newsletter")

        mock_connection.assert_called_once_with(
            "postgresql://user:secret@db/newsletter"
        )
        self.assertEqual(cursor.execute.call_count, 3)
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS source_items",
            cursor.execute.call_args_list[0].args[0],
        )


if __name__ == "__main__":
    unittest.main()
