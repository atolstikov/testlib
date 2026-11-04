#!/usr/bin/python3
"""Compare submitted CSV with the jury CSV.

Set KEY_COLUMN to a column name to match rows by a unique ID; leave it None
to match rows by position. COLUMN_RULES maps column names to rules with kind
"auto", "number", "text", or "ignore", plus abs_tol, rel_tol, inclusive,
and case_sensitive. By default all columns are compared exactly, interpreting
finite decimal pairs as numbers. ALLOW_COLUMN_REORDER controls header order.

POINTS enables scoring. SCORE_MODE is "all_or_nothing" or "fraction_correct".
In the latter mode, missing and extra rows reduce the score. The jury CSV is
passed as the answer file, not the input file.
"""

import csv
import io
from decimal import Decimal, InvalidOperation

from testlib import Outcome, ans, ouf, quitf, quitp, registerTestlibCmd

KEY_COLUMN = None
ALLOW_COLUMN_REORDER = False
COLUMN_RULES = {}
POINTS = None
SCORE_MODE = "all_or_nothing"

_KINDS = {"auto", "number", "text", "ignore"}
_RULE_FIELDS = {"kind", "abs_tol", "rel_tol", "inclusive", "case_sensitive"}


def _error(stream, message):
    stream.quitf(Outcome.PE, message)


def _read_csv(stream):
    # InStream exposes bytes as Latin-1 characters. Recover and decode the
    # original bytes before handing the content to Python's CSV parser.
    lines = []
    while not stream.eof():
        lines.append(stream.readLine())
    try:
        content = "\n".join(lines).encode("latin-1").decode("utf-8-sig")
    except UnicodeError:
        _error(stream, "CSV is not valid UTF-8")
    try:
        reader = csv.reader(io.StringIO(content, newline=""), strict=True)
        rows = list(reader)
    except csv.Error:
        _error(stream, "Malformed CSV")
    if not rows or not rows[0]:
        _error(stream, "Missing CSV header")
    header = rows[0]
    if any(not name for name in header) or len(set(header)) != len(header):
        _error(stream, "Empty or duplicate CSV column name")
    width = len(header)
    for index, row in enumerate(rows[1:], 2):
        if len(row) != width:
            _error(stream, f"Wrong number of CSV fields in row {index}")
    return header, rows[1:]


def _decimal(value):
    try:
        result = Decimal(value)
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def _tolerance(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        quitf(Outcome.FAIL, f"Invalid {name}")
    result = _decimal(str(value))
    if result is None or result < 0:
        quitf(Outcome.FAIL, f"Invalid {name}")
    return result


def _rules(header):
    if not isinstance(COLUMN_RULES, dict):
        quitf(Outcome.FAIL, "COLUMN_RULES must be a mapping")
    unknown = set(COLUMN_RULES) - set(header)
    if unknown:
        quitf(Outcome.FAIL, "Rules refer to unknown CSV columns")
    rules = {}
    for column in header:
        spec = COLUMN_RULES.get(column, {})
        if not isinstance(spec, dict) or set(spec) - _RULE_FIELDS:
            quitf(Outcome.FAIL, f"Invalid rule for column {column}")
        kind = spec.get("kind", "auto")
        if kind not in _KINDS:
            quitf(Outcome.FAIL, f"Invalid comparison kind for column {column}")
        inclusive = spec.get("inclusive", True)
        case_sensitive = spec.get("case_sensitive", True)
        if not isinstance(inclusive, bool) or not isinstance(case_sensitive, bool):
            quitf(Outcome.FAIL, f"Invalid comparison flag for column {column}")
        rules[column] = {
            "kind": kind,
            "abs_tol": _tolerance(spec.get("abs_tol", 0), "abs_tol"),
            "rel_tol": _tolerance(spec.get("rel_tol", 0), "rel_tol"),
            "inclusive": inclusive,
            "case_sensitive": case_sensitive,
        }
    return rules


def _matches(expected, found, rule):
    kind = rule["kind"]
    if kind == "ignore":
        return True
    left = _decimal(expected)
    right = _decimal(found)
    if kind == "number" and (left is None or right is None):
        return False
    if kind == "number" or (kind == "auto" and left is not None and right is not None):
        difference = abs(left - right)
        limit = max(rule["abs_tol"], rule["rel_tol"] * max(abs(left), abs(right)))
        return difference <= limit if rule["inclusive"] else difference < limit or left == right
    if rule["case_sensitive"]:
        return expected == found
    return expected.casefold() == found.casefold()


def _indexed(rows, header, stream):
    key_index = header.index(KEY_COLUMN)
    result = {}
    for row in rows:
        key = row[key_index]
        if not key or key in result:
            _error(stream, "Empty or duplicate CSV row key")
        result[key] = row
    return result


def _finish(correct, total, errors):
    summary = f"correct rows {correct}/{total}; errors {errors}"
    if POINTS is not None:
        if SCORE_MODE == "all_or_nothing":
            score = POINTS if errors == 0 else 0
        else:
            score = POINTS * correct / total if total else POINTS
        quitp(score, summary)
    quitf(Outcome.OK if errors == 0 else Outcome.WA, summary)


def main():
    registerTestlibCmd()
    if KEY_COLUMN is not None and (not isinstance(KEY_COLUMN, str) or not KEY_COLUMN):
        quitf(Outcome.FAIL, "KEY_COLUMN must be a nonempty column name")
    if not isinstance(ALLOW_COLUMN_REORDER, bool):
        quitf(Outcome.FAIL, "ALLOW_COLUMN_REORDER must be boolean")
    if SCORE_MODE not in {"all_or_nothing", "fraction_correct"}:
        quitf(Outcome.FAIL, "Invalid SCORE_MODE")
    if POINTS is not None:
        if isinstance(POINTS, bool) or not isinstance(POINTS, (int, float)):
            quitf(Outcome.FAIL, "POINTS must be an int or float")
        if _tolerance(POINTS, "POINTS") > 1_000_000:
            quitf(Outcome.FAIL, "POINTS exceeds testlib limit")
    jury_header, jury_rows = _read_csv(ans)
    if KEY_COLUMN is not None and KEY_COLUMN not in jury_header:
        quitf(Outcome.FAIL, "KEY_COLUMN missing from jury CSV")
    rules = _rules(jury_header)
    user_header, user_rows = _read_csv(ouf)
    same_columns = (
        set(user_header) == set(jury_header) if ALLOW_COLUMN_REORDER
        else user_header == jury_header
    )
    if not same_columns:
        if POINTS is None:
            quitf(Outcome.WA, "CSV columns differ")
        quitp(0, "CSV columns differ")
    expected_columns = [jury_header.index(name) for name in jury_header]
    found_columns = [user_header.index(name) for name in jury_header]

    def row_matches(expected, found):
        return all(
            _matches(expected[left], found[right], rules[name])
            for name, left, right in zip(jury_header, expected_columns, found_columns)
        )

    if KEY_COLUMN is None:
        correct = sum(row_matches(a, b) for a, b in zip(jury_rows, user_rows))
    else:
        expected = _indexed(jury_rows, jury_header, ans)
        found = _indexed(user_rows, user_header, ouf)
        correct = sum(row_matches(row, found[key]) for key, row in expected.items() if key in found)
    total = max(len(jury_rows), len(user_rows))
    _finish(correct, total, total - correct)


if __name__ == "__main__":
    main()
