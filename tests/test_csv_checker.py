"""End-to-end checks for the configurable CSV checker."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_csv(answer, output, **settings):
    with tempfile.TemporaryDirectory() as directory:
        paths = [Path(directory) / name for name in ("input", "output", "answer")]
        paths[0].write_bytes(b"")
        paths[1].write_bytes(output)
        paths[2].write_bytes(answer)
        code = "from checkers import csv_checker as checker\n"
        code += "".join(f"checker.{key} = {value!r}\n" for key, value in settings.items())
        code += "checker.main()\n"
        return subprocess.run(
            [sys.executable, "-B", "-c", code, *(str(path) for path in paths)],
            cwd=ROOT, capture_output=True, check=False,
        )


class CsvCheckerTests(unittest.TestCase):
    def test_ordered_rows_parse_quoted_commas_and_utf8(self):
        answer = 'id,name,age\n1,"Müller, Ana",29.70\n2,"Smith, Jo",40\n'.encode()
        output = 'id,name,age\n1,"Müller, Ana",29.7\n2,"Smith, Jo",40.0\n'.encode()
        result = run_csv(answer, output)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run_csv(answer, 'id,name,age\n2,"Smith, Jo",40\n1,"Müller, Ana",29.70\n'.encode())
        self.assertEqual(result.returncode, 1)

    def test_escaped_quotes_and_multiline_fields(self):
        answer = b'id,note\n1,"he said ""yes""\nthen left"\n'
        self.assertEqual(run_csv(answer, answer).returncode, 0)

    def test_keyed_rows_and_reordered_columns(self):
        answer = b'id,name,score\na,Alice,0.80\nb,Bob,0.40\n'
        output = b'score,id,name\n0.401,b,Bob\n0.799,a,Alice\n'
        settings = dict(KEY_COLUMN="id", ALLOW_COLUMN_REORDER=True,
                        COLUMN_RULES={"score": {"kind": "number", "abs_tol": 0.002}})
        self.assertEqual(run_csv(answer, output, **settings).returncode, 0)
        self.assertEqual(run_csv(answer, output, KEY_COLUMN="id").returncode, 1)

    def test_duplicate_headers_and_keys_are_rejected(self):
        answer = b'id,score\na,1\n'
        self.assertEqual(run_csv(answer, b'id,id\na,1\n').returncode, 2)
        self.assertEqual(run_csv(answer, b'id,score\na,1\na,1\n', KEY_COLUMN="id").returncode, 2)
        self.assertEqual(run_csv(b'id,score\na,1\na,2\n', b'id,score\na,1\n',
                                 KEY_COLUMN="id").returncode, 3)

    def test_wrong_width_and_malformed_quotes(self):
        answer = b'id,note\n1,ok\n'
        self.assertEqual(run_csv(answer, b'id,note\n1\n').returncode, 2)
        self.assertEqual(run_csv(answer, b'id,note\n1,"unterminated\n').returncode, 2)

    def test_per_column_rules_and_tolerance_boundary(self):
        answer = b'id,value,label,private\n1,1.00,Yes,secret\n'
        output = b'id,value,label,private\n1,1.01,YES,other\n'
        rules = {
            "value": {"kind": "number", "abs_tol": 0.01, "inclusive": False},
            "label": {"kind": "text", "case_sensitive": False},
            "private": {"kind": "ignore"},
        }
        self.assertEqual(run_csv(answer, output, COLUMN_RULES=rules).returncode, 1)
        rules["value"]["inclusive"] = True
        self.assertEqual(run_csv(answer, output, COLUMN_RULES=rules).returncode, 0)

    def test_fractional_scoring_penalizes_missing_and_extra_rows(self):
        answer = b'id,value\na,1\nb,2\n'
        output = b'id,value\na,1\nc,3\n'
        result = run_csv(answer, output, KEY_COLUMN="id", POINTS=6,
                         SCORE_MODE="fraction_correct")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stderr.startswith(b'points 3.0 '), result.stderr)
        result = run_csv(answer, output, KEY_COLUMN="id", POINTS=6)
        self.assertTrue(result.stderr.startswith(b'points 0 '), result.stderr)


if __name__ == "__main__":
    unittest.main()
