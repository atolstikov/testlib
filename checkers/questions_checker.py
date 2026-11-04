#!/usr/bin/python3
"""Check answers written as ``Q1 value``, one question per non-empty line.

Configure QUESTION_RULES per question. Each rule accepts:

    kind: "auto" (default), "number", "text", or "unordered"
    abs_tol, rel_tol: non-negative numeric tolerances (for numbers)
    case_sensitive: whether text comparisons respect case
    points: non-negative points for a correct answer
    required: whether omitting the question is WA

"auto" compares tokens in order, interpreting finite numeric pairs as
numbers. "unordered" compares text tokens as a multiset. POINTS remains
available for older checkers; a rule's points override its POINTS entry.
When scoring is enabled, omitted questions earn zero by default. Without
scoring, questions are required by default.
"""

import math
import re
from collections import Counter

from testlib import Outcome, ans, ouf, quitf, quitp, registerTestlibCmd

version = "0.2.0 (Nov 4 2026)"
REQUIRED_PRECISION = 0.0015
CASE_SENSITIVE = False
REPLACE_COMMA_TO_POINT = True
POINTS = None  # Example: {"Q1": 1, "Q2": 3}
QUESTION_RULES = {}  # Example: {"Q1": {"kind": "number", "abs_tol": 0.01, "points": 2}}
QUESTION_ID_PATTERN = re.compile(r"Q[1-9][0-9]*", re.IGNORECASE)
NUMBER_PATTERN = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
KINDS = {"auto", "number", "text", "unordered"}


def read(stream):
    answers = {}
    line_number = 0
    while not stream.eof():
        line_number += 1
        parts = stream.readLine().split()
        if not parts:
            continue
        key = parts[0].upper()
        if not QUESTION_ID_PATTERN.fullmatch(key):
            stream.quitf(Outcome.PE, f"Invalid question ID on line {line_number}")
        if key in answers:
            stream.quitf(Outcome.PE, f"Duplicate question {key} on line {line_number}")
        answers[key] = parts[1:]
    return answers


def _finite_number(token, *, comma):
    if comma:
        token = token.replace(",", ".")
    if NUMBER_PATTERN.fullmatch(token) is None:
        return None
    try:
        value = float(token)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _nonfinite_number(token, *, comma):
    if comma:
        token = token.replace(",", ".")
    try:
        return not math.isfinite(float(token))
    except ValueError:
        return False


def _rule(key, configured, weights, scoring):
    spec = dict(configured.get(key, {}))
    unknown = set(spec) - {"kind", "abs_tol", "rel_tol", "case_sensitive", "points", "required"}
    if unknown:
        quitf(Outcome.FAIL, "Unknown rule fields for {}: {}".format(key, ", ".join(sorted(unknown))))
    kind = spec.get("kind", "auto")
    if kind not in KINDS:
        quitf(Outcome.FAIL, f"Invalid comparison kind for {key}")
    for field, default in (("abs_tol", REQUIRED_PRECISION), ("rel_tol", 0.0)):
        value = spec.get(field, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            quitf(Outcome.FAIL, f"Invalid {field} for {key}")
        spec[field] = value
    case_sensitive = spec.get("case_sensitive", CASE_SENSITIVE)
    if not isinstance(case_sensitive, bool):
        quitf(Outcome.FAIL, f"Invalid case_sensitive for {key}")
    spec["case_sensitive"] = case_sensitive
    spec["kind"] = kind
    required = spec.get("required", not scoring)
    if not isinstance(required, bool):
        quitf(Outcome.FAIL, f"Invalid required for {key}")
    spec["required"] = required
    default_points = weights.get(key, 0)
    points = spec.get("points", default_points)
    if scoring and (
        isinstance(points, bool) or not isinstance(points, (int, float))
        or not math.isfinite(points) or points < 0
    ):
        quitf(Outcome.FAIL, f"Invalid points for {key}")
    spec["points"] = points
    return spec


def _rules(jury):
    if not isinstance(QUESTION_RULES, dict):
        quitf(Outcome.FAIL, "QUESTION_RULES must be a mapping")
    configured = {}
    for key, spec in QUESTION_RULES.items():
        if not isinstance(key, str):
            quitf(Outcome.FAIL, "Question rule keys must be strings")
        canonical = key.upper()
        if canonical in configured or canonical not in jury or not isinstance(spec, dict):
            quitf(Outcome.FAIL, f"Invalid rule for question {key}")
        configured[canonical] = spec
    weights = {}
    if POINTS is not None:
        if not isinstance(POINTS, dict):
            quitf(Outcome.FAIL, "POINTS must be a mapping")
        for key, value in POINTS.items():
            if not isinstance(key, str):
                quitf(Outcome.FAIL, "POINTS keys must be strings")
            canonical = key.upper()
            if canonical in weights or canonical not in jury:
                quitf(Outcome.FAIL, f"Points configured for unknown question {key}")
            if (
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0
            ):
                quitf(Outcome.FAIL, f"Invalid points for {key}")
            weights[canonical] = value
    scoring = POINTS is not None or any("points" in spec for spec in configured.values())
    rules = {key: _rule(key, configured, weights, scoring) for key in jury}
    if scoring and sum(rule["points"] for rule in rules.values()) > 1e6:
        quitf(Outcome.FAIL, "Total points exceed testlib's limit")
    return rules, scoring


def _text(token, rule):
    return token if rule["case_sensitive"] else token.casefold()


def _number(token, stream, key):
    value = _finite_number(token, comma=REPLACE_COMMA_TO_POINT)
    if value is None:
        stream.quitf(Outcome.PE, f"Invalid finite number for {key}")
    return value


def _validate_jury(tokens, rule, key):
    if rule["kind"] == "number":
        if len(tokens) != 1:
            ans.quitf(Outcome.PE, f"Expected one jury number for {key}")
        _number(tokens[0], ans, key)
    elif rule["kind"] == "auto":
        for token in tokens:
            if _nonfinite_number(token, comma=REPLACE_COMMA_TO_POINT):
                ans.quitf(Outcome.PE, f"Invalid jury number for {key}")


def _matches(expected, found, rule, key):
    kind = rule["kind"]
    if kind == "number":
        if len(found) != 1:
            ouf.quitf(Outcome.PE, f"Expected one number for {key}")
        a, b = _number(expected[0], ans, key), _number(found[0], ouf, key)
        return math.isclose(a, b, rel_tol=rule["rel_tol"], abs_tol=rule["abs_tol"])
    if kind == "text":
        return _text(" ".join(expected), rule) == _text(" ".join(found), rule)
    if kind == "unordered":
        return Counter(_text(token, rule) for token in expected) == Counter(
            _text(token, rule) for token in found
        )
    for token in found:
        if _nonfinite_number(token, comma=REPLACE_COMMA_TO_POINT):
            ouf.quitf(Outcome.PE, f"Invalid finite number for {key}")
    if len(expected) != len(found):
        return False
    for a, b in zip(expected, found):
        x = _finite_number(a, comma=REPLACE_COMMA_TO_POINT)
        y = _finite_number(b, comma=REPLACE_COMMA_TO_POINT)
        if x is not None and y is not None:
            if not math.isclose(x, y, rel_tol=rule["rel_tol"], abs_tol=rule["abs_tol"]):
                return False
        elif _text(a, rule) != _text(b, rule):
            return False
    return True


def main():
    registerTestlibCmd()
    jury = read(ans)
    if not jury:
        quitf(Outcome.FAIL, "No jury questions")
    rules, scoring = _rules(jury)
    for key, tokens in jury.items():
        _validate_jury(tokens, rules[key], key)
    participant = read(ouf)
    extra = set(participant) - set(jury)
    if extra:
        quitf(Outcome.WA, "Unexpected questions: {}".format(", ".join(sorted(extra)[:5])))
    missing = set(jury) - set(participant)
    required_missing = {key for key in missing if rules[key]["required"]}
    if required_missing:
        quitf(Outcome.WA, "Missing required questions: {}".format(
            ", ".join(sorted(required_missing)[:5])))
    correct = 0
    points = 0.0
    incorrect = []
    for key, expected in jury.items():
        if key not in participant:
            continue
        if _matches(expected, participant[key], rules[key], key):
            correct += 1
            points += rules[key]["points"]
        else:
            incorrect.append(key)
    summary = f"correct {correct}/{len(jury)}; missing {len(missing)}; incorrect {len(incorrect)}"
    if incorrect:
        summary += " ({})".format(", ".join(incorrect[:5]))
    if scoring:
        quitp(points, summary)
    if incorrect:
        quitf(Outcome.WA, summary)
    quitf(Outcome.OK, summary)


if __name__ == "__main__":
    main()
