"""Tests for the manual admin review GitHub Actions workflow."""

from pathlib import Path
import unittest


WORKFLOW_PATH = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "review-newsletter.yml"
)


class ReviewWorkflowYamlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_only_triggers_manually(self):
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertNotIn("schedule:", self.workflow)

    def test_has_issue_key_decision_and_feedback_inputs(self):
        self.assertIn("issue_key:", self.workflow)
        self.assertIn("decision:", self.workflow)
        self.assertIn("feedback:", self.workflow)
        self.assertIn("- approve", self.workflow)
        self.assertIn("- request_changes", self.workflow)

    def test_invokes_the_review_module(self):
        self.assertIn("python -m graph.review", self.workflow)
        self.assertIn("--issue-key", self.workflow)
        self.assertIn("--decision", self.workflow)
        self.assertIn("--feedback", self.workflow)


if __name__ == "__main__":
    unittest.main()
