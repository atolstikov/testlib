#!/usr/bin/python3

from testlib import *

EPS = 1.5E-6


if __name__ == '__main__':
    """
    compare two doubles, maximal absolute error EPS
    """
    registerTestlibCmd()

    ja = ans.readDouble()
    pa = ouf.readDouble()

    if abs(ja - pa) > EPS + 1E-15:
        quitf(Outcome.WA, "expected {:.10f}, found {:.10f}".format(ja, pa))

    quitf(Outcome.OK, "answer is {.10f}".format(ja))
