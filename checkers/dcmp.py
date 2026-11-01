#!/usr/bin/python3
"""Compare two doubles, maximal absolute or relative error EPS."""

from testlib import *

EPS = 1E-6


if __name__ == '__main__':
    registerTestlibCmd()

    ja = ans.readDouble()
    pa = ouf.readDouble()

    if not doubleCompare(ja, pa, EPS):
        quitf(Outcome.WA, "expected {:.10f}, found {:.10f}".format(ja, pa))

    quitf(Outcome.OK, "answer is {:.10f}".format(ja))
