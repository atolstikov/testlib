"""End-to-end checks for the Python checker and validator API."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
EOL = b"\r\n" if os.name == "nt" else b"\n"


def run_validator(body, data):
    code = "import sys\nfrom testlib import *\nregisterValidation(sys.argv)\n" + body
    return subprocess.run(
        [sys.executable, "-B", "-c", code], input=data, cwd=ROOT,
        capture_output=True, check=False,
    )


def run_checker(body, output, report=False):
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        paths = [directory / name for name in ("input", "output", "answer")]
        for path in paths:
            path.write_bytes(output if path.name == "output" else b"")
        report_path = directory / "report.xml"
        args = [str(path) for path in paths]
        if report:
            args.extend((str(report_path), "-appes"))
        code = "from testlib import *\nregisterTestlibCmd()\n" + body
        result = subprocess.run(
            [sys.executable, "-B", "-c", code, *args], cwd=ROOT,
            capture_output=True, check=False,
        )
        report_bytes = report_path.read_bytes() if report_path.exists() else None
        return result, report_bytes


class PythonTestlibTests(unittest.TestCase):
    def test_validator_reads_words_lines_and_unsigned_values(self):
        body = (
            'assert inf.readWords(2, "[a-z]+", "words") == ["ab", "cd"]\n'
            'inf.readEoln()\n'
            'assert inf.readTokens(2) == ["ef", "gh"]\n'
            'inf.readEoln()\n'
            'assert inf.readUnsignedLongs(2, 0, UINT64_MAX) == [0, UINT64_MAX]\n'
            'inf.readEoln()\n'
            'assert inf.readLines(2) == ["first", ""]\n'
            'assert inf.readStrings(1) == ["last"]\n'
            'inf.readEof()\n'
        )
        data = EOL.join((b"ab cd", b"ef gh", b"0 18446744073709551615", b"first", b"", b"last", b""))
        result = run_validator(body, data)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsigned_rejects_noncanonical_and_overflow(self):
        for token in (b"-1", b"+1", b"01", b"18446744073709551616"):
            with self.subTest(token=token):
                result = run_validator("inf.readUnsignedLong()\ninf.readEof()\n", token)
                self.assertEqual(result.returncode, 3)
                self.assertIn(b"Expected unsigned integer", result.stderr)

    def test_range_error_has_array_index(self):
        result = run_validator(
            'inf.readUnsignedLongs(2, 0, 3, "values", indexBase=4)\n', b"1 4"
        )
        self.assertEqual(result.returncode, 3)
        self.assertIn(b"values[5]", result.stderr)

    def test_signed_integer_limits_and_bounds(self):
        body = (
            'assert inf.readInt() == -2147483648\n'
            'inf.readSpace()\n'
            'assert inf.readLong() == 9223372036854775807\n'
            'inf.readEof()\n'
        )
        result = run_validator(body, b"-2147483648 9223372036854775807")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run_validator('inf.readInt()\n', b"2147483648")
        self.assertEqual(result.returncode, 3)
        self.assertIn(b"int32", result.stderr)
        result = run_validator('inf.readInt(1, 100, "n")\n', b"101")
        self.assertEqual(result.returncode, 3)
        self.assertIn(b"violates the range", result.stderr)

    def test_strict_token_spacing_and_line_ending(self):
        result = run_validator('inf.readWords(2)\ninf.readEof()\n', b"one  two")
        self.assertEqual(result.returncode, 3)
        self.assertIn(b"Unexpected white-space", result.stderr)
        result = run_validator('inf.readLines(1)\ninf.readEof()\n', b"line")
        self.assertEqual(result.returncode, 3)
        self.assertIn(b"Expected EOLN", result.stderr)

    def test_validator_requires_read_eof(self):
        result = run_validator("inf.readInt()\n", b"1")
        self.assertEqual(result.returncode, 3)
        self.assertIn(b"Validator must end with readEof", result.stderr)

    def test_checker_uses_whitespace_and_reports_points(self):
        body = (
            'assert ouf.readWords(2) == ["ab", "cd"]\n'
            'quitp(0.5, "partial")\n'
        )
        result, report = run_checker(body, b"  ab\n\n cd  ", report=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'outcome = "points" points = "0.5"', report)
        self.assertIn(b"0.5 partial", report)

    def test_checker_rejects_unread_output(self):
        result, _ = run_checker('ouf.readWord()\nquitf(Outcome.OK, "ok")\n', b"one two")
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"Extra information", result.stderr)

    def test_checker_pattern_error_and_xml_escaping(self):
        result, _ = run_checker(
            'ouf.readTokens(2, "[a-z]+", "tokens")\nquitf(Outcome.OK, "ok")\n',
            b"ab 42",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"tokens[2]", result.stderr)
        result, report = run_checker('quitf(Outcome.OK, "<&\\\"")\n', b"", report=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"&lt;&amp;&quot;", report)

    def test_strict_real_alias(self):
        result = run_validator(
            'assert inf.readStrictReals(2, 0, 1, 1, 2) == [0.5, 1.0]\n'
            'inf.readEoln()\ninf.readEof()\n',
            b"0.5 1.0" + EOL,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
