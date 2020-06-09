#!/usr/bin/python3

from testlib import *

EPS = 1E-6


if __name__ == '__main__':
    """
    compare two doubles, maximal absolute or relative error EPS
    """
    registerTestlibCmd()

    ja = ans.readDouble()
    pa = ouf.readDouble()

    if doubleCompare(ja, pa, EPS):
        quitf(Outcome.WA, "expected {:.10f}, found {:.10f}".format(ja, pa))

    quitf(Outcome.OK, "answer is {.10f}".format(ja))
