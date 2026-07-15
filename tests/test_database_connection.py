"""Tests for PostgreSQL configuration and the connection boundary."""

import os
import unittest
from unittest.mock import MagicMock, patch

from database.connection import (
    DatabaseConfigurationError,
    check_database_connection,
    get_connect_timeout_seconds,
    get_database_url,
)


class DatabaseConfigurationTests(unittest.TestCase):
    def test_database_url_is_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(DatabaseConfigurationError, "DATABASE_URL"):
                get_database_url()

    def test_database_url_is_trimmed(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "  postgresql://user:secret@db/newsletter  "},
            clear=True,
        ):
            self.assertEqual(
                get_database_url(),
                "postgresql://user:secret@db/newsletter",
            )

    def test_timeout_must_be_positive_integer(self):
        for value in ("zero", "0", "-1"):
            with self.subTest(value=value):
                with patch.dict(
                    os.environ,
                    {"DATABASE_CONNECT_TIMEOUT_SECONDS": value},
                    clear=True,
                ):
                    with self.assertRaises(DatabaseConfigurationError):
                        get_connect_timeout_seconds()


class DatabaseConnectionTests(unittest.TestCase):
    @patch("database.connection.psycopg.connect")
    def test_connection_check_runs_select_one(self, mock_connect):
        connection = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        connection.cursor.return_value.__enter__.return_value = cursor
        mock_connect.return_value.__enter__.return_value = connection

        with patch.dict(
            os.environ,
            {"DATABASE_CONNECT_TIMEOUT_SECONDS": "7"},
            clear=True,
        ):
            check_database_connection("postgresql://user:secret@db/newsletter")

        mock_connect.assert_called_once_with(
            "postgresql://user:secret@db/newsletter",
            connect_timeout=7,
            application_name="ai-newsletter",
        )
        cursor.execute.assert_called_once_with("SELECT 1")


if __name__ == "__main__":
    unittest.main()
