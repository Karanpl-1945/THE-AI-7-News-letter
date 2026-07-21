import unittest
from unittest.mock import patch

from agents.editor import _leftover_items, create_editorial
from llm.groq_client import GroqQuotaExhaustedError


def _items(prefix: str, count: int, start: int = 0):
    return [
        {
            "title": f"{prefix} {index}",
            "summary": f"Summary for {prefix} {index}",
            "why_it_matters": f"Why {prefix} {index} matters",
            "key_takeaway": f"Takeaway for {prefix} {index}",
            "url": f"https://example.com/{prefix.lower()}/{index}",
            "docs_url": f"https://docs.example.com/{prefix.lower()}/{index}",
            "difficulty": "Intermediate",
            "tags": [prefix.lower(), "ai"],
        }
        for index in range(start, start + count)
    ]


def _state():
    return {
        "summarized_papers": _items("Paper", 7),
        "summarized_models": _items("Model", 4),
        "summarized_github": _items("GitHub", 7),
        "summarized_frameworks": _items("Framework", 4),
        "summarized_news": _items("News", 5),
    }


def _state_with_leftovers():
    """Adds raw/selected pairs so leftover computation has something to work with."""
    state = _state()
    state["selected_papers"] = _items("Paper", 8)
    state["papers"] = _items("Paper", 8) + _items("Paper", 3, start=8)  # 3 genuine leftovers
    return state


CORE_RESPONSE = {
    "tldr": [f"Bullet {index}" for index in range(5)],
    "paper_of_week": {
        "problem": "Problem",
        "approach": "Approach",
        "results": "Results",
        "why_you_should_care": "Reason",
        "takeaway": "One line.",
    },
    "tool_of_week": {
        "what_it_is": "Tool description",
        "whats_new": "New behavior",
        "comparison": "Comparison",
        "install_cmd": "pip install example",
        "quickstart_code": "import example",
        "who_should_use": "Developers",
    },
}

EXTRAS_RESPONSE = {
    "research_radar": [{"title": "Paper 8", "one_liner": "Advances retrieval quality."}],
    "emerging_patterns": [],
    "production_playbook": {},
    "under_the_radar": {},
    "quick_hits": ["One-line mention."],
    "glossary": [{"term": "Agent", "definition": "A system."}],
    "learning_paths": ["Read the guide"],
    "trending_topics": ["agents"],
}


class LeftoverItemsTests(unittest.TestCase):
    def test_excludes_items_already_selected_by_url(self):
        selected = [{"title": "A", "url": "https://example.com/a"}]
        full = [
            {"title": "A", "url": "https://example.com/a"},
            {"title": "B", "url": "https://example.com/b"},
        ]

        leftover = _leftover_items(full, selected)

        self.assertEqual([item["title"] for item in leftover], ["B"])

    def test_excludes_items_already_selected_by_normalized_title(self):
        selected = [{"title": "Some Paper!", "url": ""}]
        full = [{"title": "some paper", "url": ""}, {"title": "Other Paper", "url": ""}]

        leftover = _leftover_items(full, selected)

        self.assertEqual([item["title"] for item in leftover], ["Other Paper"])

    def test_caps_at_the_configured_limit(self):
        full = [{"title": f"Item {i}", "url": f"https://example.com/{i}"} for i in range(20)]

        leftover = _leftover_items(full, [])

        self.assertEqual(len(leftover), 8)


class EditorTests(unittest.TestCase):
    def test_editor_runs_two_independent_calls_and_preserves_output_contract(self):
        with patch(
            "agents.editor._call", side_effect=[CORE_RESPONSE, EXTRAS_RESPONSE]
        ) as groq_call:
            result = create_editorial(_state_with_leftovers())

        self.assertEqual(groq_call.call_count, 2)
        self.assertEqual(groq_call.call_args_list[0].kwargs["max_tokens"], 900)
        self.assertEqual(groq_call.call_args_list[1].kwargs["max_tokens"], 1200)

        self.assertEqual(len(result["top_papers"]), 5)
        self.assertEqual(len(result["top_models"]), 3)
        self.assertEqual(len(result["top_github"]), 5)
        self.assertEqual(len(result["top_frameworks"]), 3)
        self.assertEqual(len(result["top_news"]), 4)

        self.assertEqual(result["paper_of_week"]["title"], "Paper 0")
        self.assertEqual(result["paper_of_week"]["url"], "https://example.com/paper/0")
        self.assertEqual(result["paper_of_week"]["takeaway"], "One line.")
        self.assertEqual(result["tool_of_week"]["name"], "Framework 0")

        self.assertEqual(result["glossary"], [{"term": "Agent", "definition": "A system."}])
        self.assertEqual(result["quick_hits"], ["One-line mention."])
        # research_radar entry must be anchored to a real leftover item, url included
        self.assertEqual(
            result["research_radar"],
            [{"title": "Paper 8", "url": "https://example.com/paper/8", "one_liner": "Advances retrieval quality."}],
        )

    def test_extras_failure_never_touches_core_content(self):
        """The key independence guarantee: a bad extras call must not blank out page 1."""
        with patch(
            "agents.editor._call",
            side_effect=[CORE_RESPONSE, RuntimeError("Groq JSON response must be an object")],
        ):
            result = create_editorial(_state_with_leftovers())

        self.assertEqual(result["paper_of_week"]["title"], "Paper 0")
        self.assertEqual(result["paper_of_week"]["problem"], "Problem")
        self.assertEqual(result["tool_of_week"]["what_it_is"], "Tool description")
        self.assertEqual(result["tldr"], [f"Bullet {i}" for i in range(5)])
        # Extras degrade gracefully instead
        self.assertEqual(result["glossary"], [])
        self.assertEqual(result["research_radar"], [])
        self.assertEqual(result["quick_hits"], [])

    def test_core_failure_never_touches_extras_content(self):
        with patch(
            "agents.editor._call",
            side_effect=[RuntimeError("quota exhausted"), EXTRAS_RESPONSE],
        ):
            result = create_editorial(_state_with_leftovers())

        # Anchoring still attaches a real title/url even on a core fallback —
        # only the Groq-authored narrative fields (problem/approach/...) are absent.
        self.assertEqual(result["paper_of_week"]["title"], "Paper 0")
        self.assertNotIn("problem", result["paper_of_week"])
        self.assertEqual(result["tool_of_week"]["name"], "Framework 0")
        self.assertNotIn("what_it_is", result["tool_of_week"])
        self.assertEqual(len(result["tldr"]), 5)  # deterministic fallback tldr
        self.assertEqual(result["glossary"], [{"term": "Agent", "definition": "A system."}])
        self.assertEqual(result["quick_hits"], ["One-line mention."])

    def test_partial_core_response_normalizes_invalid_and_missing_fields(self):
        generated = {
            "tldr": ["Valid bullet", 123, ""],
            "paper_of_week": "not an object",
            "tool_of_week": {"what_it_is": "Valid tool", "comparison": 42},
        }

        with patch("agents.editor._call", side_effect=[generated, {}]):
            result = create_editorial(_state())

        self.assertEqual(result["tldr"], ["Valid bullet"])
        self.assertEqual(result["paper_of_week"]["title"], "Paper 0")
        self.assertEqual(result["tool_of_week"]["what_it_is"], "Valid tool")
        self.assertNotIn("comparison", result["tool_of_week"])

    def test_core_response_with_no_usable_fields_uses_deterministic_fallback(self):
        generated = {"tldr": "not a list", "paper_of_week": None, "tool_of_week": 123}

        with patch("agents.editor._call", side_effect=[generated, {}]):
            result = create_editorial(_state())

        self.assertEqual(len(result["tldr"]), 5)
        self.assertEqual(result["paper_of_week"]["title"], "Paper 0")
        self.assertNotIn("problem", result["paper_of_week"])

    def test_research_radar_drops_entries_with_no_matching_supplied_title(self):
        hallucinated = {**EXTRAS_RESPONSE, "research_radar": [
            {"title": "A paper that does not exist", "one_liner": "Made up."}
        ]}

        with patch("agents.editor._call", side_effect=[CORE_RESPONSE, hallucinated]):
            result = create_editorial(_state_with_leftovers())

        self.assertEqual(result["research_radar"], [])

    def test_editorial_feedback_is_included_in_the_core_prompt_when_present(self):
        with patch("agents.editor._call", side_effect=[{}, {}]) as groq_call:
            create_editorial({**_state(), "editorial_feedback": "Cut the tool of the week section."})

        core_prompt = groq_call.call_args_list[0].args[0]
        self.assertIn("The admin reviewed the previous draft", core_prompt)
        self.assertIn("Cut the tool of the week section.", core_prompt)

    def test_editorial_feedback_is_absent_from_the_prompt_by_default(self):
        with patch("agents.editor._call", side_effect=[{}, {}]) as groq_call:
            create_editorial(_state())

        core_prompt = groq_call.call_args_list[0].args[0]
        self.assertNotIn("The admin reviewed the previous draft", core_prompt)

    def test_core_rate_limit_propagates_and_skips_extras_entirely(self):
        quota_error = GroqQuotaExhaustedError("daily quota exhausted", retry_after_seconds=900)

        with patch("agents.editor._call", side_effect=quota_error) as groq_call:
            with self.assertRaises(GroqQuotaExhaustedError):
                create_editorial(_state())

        groq_call.assert_called_once()  # extras never attempted

    def test_extras_rate_limit_propagates(self):
        quota_error = GroqQuotaExhaustedError("daily quota exhausted", retry_after_seconds=900)

        with patch("agents.editor._call", side_effect=[CORE_RESPONSE, quota_error]):
            with self.assertRaises(GroqQuotaExhaustedError):
                create_editorial(_state())


if __name__ == "__main__":
    unittest.main()
