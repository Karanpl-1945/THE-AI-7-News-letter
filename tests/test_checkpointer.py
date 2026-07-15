"""Tests for LangGraph PostgreSQL checkpoint initialization."""

import os
import unittest
from unittest.mock import MagicMock, patch

from database.checkpointer import (
    LANGGRAPH_CHECKPOINT_TABLES,
    initialize_checkpoint_storage,
)


class CheckpointerTests(unittest.TestCase):
    @patch("database.checkpointer.PostgresSaver.from_conn_string")
    def test_initializer_runs_langgraph_setup(self, mock_from_conn_string):
        checkpointer = MagicMock()
        mock_from_conn_string.return_value.__enter__.return_value = checkpointer

        initialize_checkpoint_storage("postgresql://user:secret@db/newsletter")

        mock_from_conn_string.assert_called_once_with(
            "postgresql://user:secret@db/newsletter"
        )
        checkpointer.setup.assert_called_once_with()

    @patch("database.checkpointer.PostgresSaver.from_conn_string")
    def test_initializer_reads_database_url_from_environment(
        self,
        mock_from_conn_string,
    ):
        checkpointer = MagicMock()
        mock_from_conn_string.return_value.__enter__.return_value = checkpointer

        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:secret@db/from-environment"},
            clear=True,
        ):
            initialize_checkpoint_storage()

        mock_from_conn_string.assert_called_once_with(
            "postgresql://user:secret@db/from-environment"
        )
        checkpointer.setup.assert_called_once_with()

    def test_expected_managed_table_names_are_documented(self):
        self.assertEqual(
            LANGGRAPH_CHECKPOINT_TABLES,
            (
                "checkpoint_migrations",
                "checkpoints",
                "checkpoint_blobs",
                "checkpoint_writes",
            ),
        )


if __name__ == "__main__":
    unittest.main()
