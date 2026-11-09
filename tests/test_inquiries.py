import logging
import unittest
from types import SimpleNamespace

from mediator.inquiries import Inquiries


class InquiriesTests(unittest.TestCase):
    def test_generate_extracts_questions_and_deduplicates(self) -> None:
        mediator = SimpleNamespace(
            state=SimpleNamespace(
                complaint="I was denied a hearing.",
                inquiries=[],
            ),
            query_backend=lambda prompt: (
                "When did the denial happen?\n"
                "What notice did you receive?\n"
                "When did the denial happen?"
            ),
        )
        inquiries = Inquiries(mediator)

        inquiries.generate()

        self.assertEqual(len(mediator.state.inquiries), 2)
        self.assertEqual(mediator.state.inquiries[0]["question"], "When did the denial happen?")
        self.assertEqual(mediator.state.inquiries[0]["alternative_questions"], ["When did the denial happen?"])
        self.assertEqual(mediator.state.inquiries[1]["question"], "What notice did you receive?")

    def test_answer_and_completion_handle_empty_state(self) -> None:
        mediator = SimpleNamespace(
            state=SimpleNamespace(
                complaint="I was denied a hearing.",
                inquiries=[],
            ),
            query_backend=lambda prompt: "",
        )
        inquiries = Inquiries(mediator)

        inquiries.answer("No-op")
        self.assertTrue(inquiries.is_complete())

        mediator.state.inquiries.append(
            {"question": "What date was the notice?", "alternative_questions": [], "answer": None}
        )
        self.assertFalse(inquiries.is_complete())

        inquiries.answer("March 1, 2026")
        self.assertEqual(mediator.state.inquiries[0]["answer"], "March 1, 2026")
        self.assertTrue(inquiries.is_complete())

    def test_get_next_prioritizes_support_gap_then_dependency_then_priority(self) -> None:
        mediator = SimpleNamespace(
            state=SimpleNamespace(
                complaint="I was denied a hearing.",
                inquiries=[
                    {
                        "question": "What happened first?",
                        "alternative_questions": [],
                        "answer": None,
                        "priority": "High",
                        "support_gap_targeted": False,
                        "dependency_gap_targeted": False,
                    },
                    {
                        "question": "Who at HACC made the decision?",
                        "alternative_questions": [],
                        "answer": None,
                        "priority": "Medium",
                        "support_gap_targeted": True,
                        "dependency_gap_targeted": True,
                    },
                    {
                        "question": "What notice did you receive?",
                        "alternative_questions": [],
                        "answer": None,
                        "priority": "Critical",
                        "support_gap_targeted": True,
                        "dependency_gap_targeted": False,
                    },
                ],
            ),
            query_backend=lambda prompt: "",
        )
        inquiries = Inquiries(mediator)

        selected = inquiries.get_next()

        self.assertIsNotNone(selected)
        self.assertEqual(selected["question"], "Who at HACC made the decision?")

    def test_gap_context_builder_failure_is_logged_and_phase_summary_is_used(self) -> None:
        class PhaseManager:
            @staticmethod
            def get_phase_data(phase, key):
                return {
                    "expected_objectives": ["timeline", "documents"],
                    "covered_objectives": ["documents"],
                    "uncovered_objectives": ["timeline"],
                }

        def fail_to_build_context():
            raise RuntimeError("gap builder unavailable")

        mediator = SimpleNamespace(
            state=SimpleNamespace(inquiries=[]),
            build_inquiry_gap_context=fail_to_build_context,
            phase_manager=PhaseManager(),
        )
        inquiries = Inquiries(mediator)

        with self.assertLogs("mediator.inquiries", level=logging.WARNING) as captured:
            context = inquiries._build_gap_context()

        self.assertEqual(context["intake_expected_objectives"], ["timeline", "documents"])
        self.assertEqual(context["intake_covered_objectives"], ["documents"])
        self.assertEqual(context["intake_uncovered_objectives"], ["timeline"])
        self.assertTrue(any("Unable to build inquiry gap context" in message for message in captured.output))
        self.assertIsNotNone(captured.records[0].exc_info)

    def test_phase_summary_failure_is_logged_and_builder_context_is_preserved(self) -> None:
        class PhaseManager:
            @staticmethod
            def get_phase_data(phase, key):
                raise RuntimeError("phase store unavailable")

        expected_context = {"priority_terms": ["denial notice"], "gap_count": 1}
        mediator = SimpleNamespace(
            state=SimpleNamespace(inquiries=[]),
            build_inquiry_gap_context=lambda: expected_context,
            phase_manager=PhaseManager(),
        )
        inquiries = Inquiries(mediator)

        with self.assertLogs("mediator.inquiries", level=logging.WARNING) as captured:
            context = inquiries._build_gap_context()

        self.assertIs(context, expected_context)
        self.assertTrue(
            any("Unable to load persisted intake priority summary" in message for message in captured.output)
        )
        self.assertIsNotNone(captured.records[0].exc_info)


if __name__ == "__main__":
    unittest.main()
