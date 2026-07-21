"""Tests for the CI workflow that runs the test suite on every push/PR."""

from pathlib import Path
import unittest


WORKFLOW_PATH = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "ci.yml"
)


class CIWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_triggers_on_push_and_pull_request_to_main(self):
        self.assertIn("push:", self.workflow)
        self.assertIn("pull_request:", self.workflow)
        self.assertIn("branches: [main]", self.workflow)

    def test_runs_the_test_suite(self):
        self.assertIn("python -m unittest discover tests", self.workflow)

    def test_does_not_reference_any_secrets(self):
        """CI should never need production credentials to verify the code."""
        self.assertNotIn("secrets.", self.workflow)


if __name__ == "__main__":
    unittest.main()
