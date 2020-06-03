#!/usr/bin/python3

from testlib import *


if __name__ == '__main__':
    """
    compare ordered sequences of signed integer numbers
    """

    registerTestlibCmd()

    n = 0
    elements = []

    while not ans.seekEof() and not ouf.seekEof():
        n += 1
        j = ans.readLong()
        p = ouf.readLong()
        if j != p:
            quitf(Outcome.WA, "{}{} numbers differ - expected: '{}', found: '{}'".format(n, englishEnding(n), j, p))
        else:
            elements.append(j)

    extra_in_ans_count = 0

    while not ans.seekEof():
        ans.readLong()
        extra_in_ans_count += 1

    extra_in_out_count = 0

    while not ouf.seekEof():
        ouf.readLong()
        extra_in_out_count += 1

    if extra_in_ans_count > 0:
        quitf(Outcome.WA,
              "Answer contains longer sequence [length = {}], but output contains {} elements"
              .format(n + extra_in_ans_count, n))

    if extra_in_out_count > 0:
        quitf(Outcome.WA,
              "Output contains longer sequence [length = {}], but answer contains {} elements"
              .format(n + extra_in_out_count, n))

    if n <= 5:
        quitf(Outcome.OK, "{} number(s): \"{}\"".format(n, compress(" ".join(map(str, elements)))))
    else:
        quitf(Outcome.OK, "{} numbers".format(n))
