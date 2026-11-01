#!/usr/bin/python3
"""Compare survey answers line by line.

Each non-empty line is a question id and its answers, for example
``Q1 answer_1`` or ``Q2 answer_2_1 answer_2_2``.
"""

version = "0.1.0 (Jan 13 2022)"

from testlib import *
import math


REQUIRED_PRECISION = 0.0015
CASE_SENSITIVE = False
REPLACE_COMMA_TO_POINT = True
POINTS = None # Ex. {"Q1": 1, "Q2": 3, ...}


def read(stream):
    result = {}
    while not stream.eof():
        line = stream.readLine().strip()
        if not line:
            continue
        if REPLACE_COMMA_TO_POINT:
            line = line.replace(',', '.')
        if not CASE_SENSITIVE:
            line = line.lower()
        items = line.split()
        result[items[0]] = items[1:]
    return result


def compare(expected, found):
    if type(expected) == list:
        if type(found) != list:
            return False
        if len(expected) != len(found):
            return False
        for e, f in zip(expected, found):
            if not compare(e, f):
                return False
    else:
        if expected == found:
            return True
        try:
            f_expected = float(expected)
            f_found = float(found)
            return math.fabs(f_expected - f_found) < REQUIRED_PRECISION
        except Exception as epx:
            return False
    return True


if __name__ == '__main__':
    registerTestlibCmd()

    jury_answer = read(ans)
    participant_answer = read(ouf)

    score = 0
    all_ok = True
    comments = []

    if sorted(jury_answer.keys()) != sorted(participant_answer.keys()):
        quitf(Outcome.WA, "Wrong set of questions: expected {}, found {}".format(
            list(jury_answer.keys()), list(participant_answer.keys()))
        )

    for key in jury_answer.keys():
        if not compare(jury_answer[key], participant_answer[key]):
            comments.append("Wrong answer for key [{}]: expected '{}', found '{}'".format(
                key, jury_answer[key], participant_answer[key]))
            all_ok = False
        else:
            if POINTS is not None and key in POINTS:
                score += POINTS[key]



    if POINTS is not None:
        quitp(score,  " | ".join(comments))
    else:    
        if all_ok == False:
            quitf(Outcome.WA, " | ".join(comments))
        else:
            quitf(Outcome.OK, "answer is {}".format(participant_answer))
