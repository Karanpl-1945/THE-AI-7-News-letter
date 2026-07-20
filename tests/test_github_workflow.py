"""Tests for the scheduled GitHub Actions newsletter workflow."""

from pathlib import Path
import unittest


WORKFLOW_PATH = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "weekly-newsletter.yml"
)


class GitHubWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_schedule_is_daily_at_eight_am_ist(self):
        self.assertIn('cron: "30 2 * * *"', self.workflow)

    def test_manual_trigger_and_force_option_remain_available(self):
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertIn("force_new_run:", self.workflow)

    def test_scheduled_and_manual_runs_are_classified_separately(self):
        self.assertIn("github.event_name == 'schedule'", self.workflow)
        self.assertIn("'github_schedule'", self.workflow)
        self.assertIn("'github_manual'", self.workflow)

    def test_scheduled_workflow_does_not_send_email(self):
        self.assertIn("python main.py --dry-run", self.workflow)


if __name__ == "__main__":
    unittest.main()
