"""Tests for checkpoint-aware pipeline execution."""

from datetime import datetime
import unittest
from unittest.mock import MagicMock

from graph.pipeline import build_thread_id, invoke_checkpointed_pipeline


class ThreadIdTests(unittest.TestCase):
    def test_weekly_thread_id_is_stable(self):
        morning = datetime(2026, 7, 15, 8, 0)
        evening = datetime(2026, 7, 15, 20, 0)

        self.assertEqual(build_thread_id(morning), "newsletter-2026-W29")
        self.assertEqual(build_thread_id(evening), "newsletter-2026-W29")

    def test_forced_thread_id_is_separate(self):
        now = datetime(2026, 7, 15, 8, 30, 45, 123456)

        self.assertEqual(
            build_thread_id(now, force=True),
            "newsletter-2026-W29-forced-20260715T083045123456",
        )


class CheckpointExecutionTests(unittest.TestCase):
    def setUp(self):
        self.pipeline = MagicMock()
        self.initial_state = {"issue_date": "July 15, 2026"}
        self.config = {"configurable": {"thread_id": "newsletter-2026-W29"}}

    def test_new_thread_starts_with_initial_state(self):
        self.pipeline.get_state.return_value = MagicMock(values={}, next=())
        expected = {**self.initial_state, "email_sent": False}
        self.pipeline.invoke.return_value = expected

        result = invoke_checkpointed_pipeline(
            self.pipeline,
            self.initial_state,
            self.config,
        )

        self.pipeline.invoke.assert_called_once_with(
            self.initial_state,
            config=self.config,
        )
        self.assertEqual(result, expected)

    def test_incomplete_thread_resumes_without_new_input(self):
        self.pipeline.get_state.return_value = MagicMock(
            values={"issue_date": "July 15, 2026"},
            next=("summarize",),
        )
        expected = {**self.initial_state, "email_sent": False}
        self.pipeline.invoke.return_value = expected

        result = invoke_checkpointed_pipeline(
            self.pipeline,
            self.initial_state,
            self.config,
        )

        self.pipeline.invoke.assert_called_once_with(None, config=self.config)
        self.assertEqual(result, expected)

    def test_completed_thread_reuses_saved_state(self):
        saved = {"issue_date": "July 15, 2026", "email_sent": False}
        self.pipeline.get_state.return_value = MagicMock(values=saved, next=())

        result = invoke_checkpointed_pipeline(
            self.pipeline,
            self.initial_state,
            self.config,
        )

        self.pipeline.invoke.assert_not_called()
        self.assertEqual(result, saved)


if __name__ == "__main__":
    unittest.main()
