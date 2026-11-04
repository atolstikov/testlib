"""End-to-end behavior of the configurable questionnaire checker."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_questions(answer, output, *, points=None, rules=None):
    with tempfile.TemporaryDirectory() as directory:
        paths = [Path(directory) / name for name in ("input", "output", "answer")]
        paths[0].write_bytes(b"")
        paths[1].write_bytes(output)
        paths[2].write_bytes(answer)
        code = (
            "from checkers import questions_checker as checker\n"
            f"checker.POINTS = {points!r}\n"
            f"checker.QUESTION_RULES = {rules or {}!r}\n"
            "checker.main()\n"
        )
        return subprocess.run(
            [sys.executable, "-B", "-c", code, *(str(path) for path in paths)],
            cwd=ROOT, capture_output=True, check=False,
        )


class QuestionsCheckerTests(unittest.TestCase):
    def test_default_ordered_text_and_numeric_tolerance(self):
        result = run_questions(
            b"Q1 Alpha beta\nQ2 1.5\n",
            b"q2 1,501\nq1 ALPHA BETA\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_duplicates_and_invalid_ids_are_format_errors(self):
        for output in (b"Q1 yes\nQ1 no\n", b"Q0 yes\n"):
            with self.subTest(output=output):
                result = run_questions(b"Q1 yes\n", output)
                self.assertEqual(result.returncode, 2)
        result = run_questions(b"Q1 yes\nQ1 no\n", b"Q1 yes\n")
        self.assertEqual(result.returncode, 3)

    def test_nonfinite_numbers_are_rejected(self):
        for output in (b"Q1 nan\n", b"Q1 inf\n", b"Q1 1e999\n"):
            with self.subTest(output=output):
                result = run_questions(b"Q1 1\n", output)
                self.assertEqual(result.returncode, 2)
        result = run_questions(b"Q1 nan\n", b"Q1 nan\n")
        self.assertEqual(result.returncode, 3)

    def test_scoring_grants_zero_for_missing_question(self):
        result = run_questions(
            b"Q1 yes\nQ2 no\n", b"Q1 yes\n", points={"q1": 2, "Q2": 3}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stderr.startswith(b"points 2.0 "), result.stderr)
        self.assertIn(b"missing 1", result.stderr)

    def test_required_policy_can_override_scoring_default(self):
        result = run_questions(
            b"Q1 yes\nQ2 no\n", b"Q1 yes\n",
            rules={
                "Q1": {"points": 2},
                "Q2": {"points": 3, "required": True},
            },
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"Missing required questions: Q2", result.stderr)
        result = run_questions(
            b"Q1 yes\nQ2 no\n", b"Q1 yes\n",
            rules={"Q2": {"required": False}},
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rules_select_number_text_and_unordered_answers(self):
        result = run_questions(
            b"Q1 100\nQ2 A,B\nQ3 red blue red\n",
            b"Q3 BLUE red RED\nQ2 a,b\nQ1 101\n",
            rules={
                "Q1": {"kind": "number", "abs_tol": 0, "rel_tol": 0.02, "points": 2},
                "Q2": {"kind": "text", "points": 1},
                "Q3": {"kind": "unordered", "points": 3},
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stderr.startswith(b"points 6.0 "), result.stderr)
        result = run_questions(
            b"Q1 red red blue\n", b"Q1 red blue blue\n",
            rules={"Q1": {"kind": "unordered"}},
        )
        self.assertEqual(result.returncode, 1)

    def test_number_rule_rejects_nonstandard_literal(self):
        result = run_questions(
            b"Q1 10\n", b"Q1 1_0\n",
            rules={"Q1": {"kind": "number"}},
        )
        self.assertEqual(result.returncode, 2)

    def test_feedback_does_not_disclose_jury_values(self):
        result = run_questions(b"Q1 secret-answer\n", b"Q1 wrong\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"Q1", result.stderr)
        self.assertNotIn(b"secret-answer", result.stderr)
        result = run_questions(b"Q1 secret-answer\n", b"Q1 wrong\n", points={"Q1": 3})
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.stderr.startswith(b"points 0.0 "), result.stderr)
        self.assertNotIn(b"secret-answer", result.stderr)


if __name__ == "__main__":
    unittest.main()
