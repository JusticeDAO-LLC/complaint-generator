from types import SimpleNamespace
import unittest

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


if __name__ == "__main__":
    unittest.main()
