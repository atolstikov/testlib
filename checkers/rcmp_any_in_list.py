#!/usr/bin/python3
"""Compare a double with a list of correct answers, maximal absolute error EPS."""

from testlib import *

EPS = 1.5E-6


if __name__ == '__main__':
    registerTestlibCmd()

    pa = ouf.readDouble()
    _ja = []
    while not ans.seekEof():
        ja = ans.readDouble()
        _ja.append(ja)

        if abs(ja - pa) <= EPS + 1E-15:
            quitf(Outcome.OK, "answer is {:.10f}".format(pa))

    if not _ja:
        quitf(Outcome.FAIL, "Answer contains no numbers")

    quitf(Outcome.WA, "expected {}, found {:.10f}".format(_ja[0] if len(_ja) == 1 else _ja, pa))
