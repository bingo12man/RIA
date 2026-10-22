import unittest

from ria1.cloud.context_gate import route_message


class TestContextGate(unittest.TestCase):

    def setUp(self):
        self.memories = {"instrument": "guitar"}

    def route(self, text, history=None):
        return route_message(
            text, history or [], self.memories
        )

    def test_instrument_recall(self):
        result = self.route(
            "What instrument am I learning?"
        )
        self.assertEqual(
            result["memories"],
            {"instrument": "guitar"},
        )

    def test_specific_guitar_question(self):
        result = self.route(
            "How do I improve chord changes?"
        )
        self.assertEqual(
            result["memories"],
            {"instrument": "guitar"},
        )

    def test_python_problem_excludes_guitar(self):
        result = self.route(
            "Something isn't working in my Python project."
        )
        self.assertEqual(result["memories"], {})

    def test_vague_problem_excludes_guitar(self):
        result = self.route("Ria, I'm struggling.")
        self.assertEqual(result["action"], "clarify")
        self.assertEqual(result["memories"], {})

    def test_unclear_next_step(self):
        result = self.route(
            "I feel confused about my next step."
        )
        self.assertEqual(result["action"], "clarify")
        self.assertEqual(result["memories"], {})

    def test_garbled_input(self):
        result = self.route(
            "airea havari duntu le"
        )
        self.assertEqual(result["action"], "clarify")
        self.assertEqual(result["memories"], {})

    def test_followup_uses_context(self):
        history = [
            {
                "role": "user",
                "content": "I'm learning guitar chords.",
            },
            {
                "role": "assistant",
                "content": "Which chords?",
            },
        ]

        result = self.route(
            "How can I improve them?",
            history,
        )

        self.assertEqual(
            result["memories"],
            {"instrument": "guitar"},
        )

    def test_unrelated_question(self):
        result = self.route(
            "What is a Python dictionary?"
        )
        self.assertEqual(result["memories"], {})

    def test_unrelated_followup(self):
        history = [
            {
                "role": "user",
                "content": "I'm learning Python.",
            },
        ]
        result = self.route(
            "How do I improve it?",
            history,
        )
        self.assertEqual(result["memories"], {})


if __name__ == "__main__":
    unittest.main()
