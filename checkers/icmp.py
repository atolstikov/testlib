#!/usr/bin/python3
"""Compare two signed 32-bit integers."""

from testlib import *


if __name__ == '__main__':
    registerTestlibCmd()
    ja = ans.readInt()
    pa = ouf.readInt()
    if ja != pa:
        quitf(Outcome.WA, "expected {}, found {}".format(ja, pa))
    quitf(Outcome.OK, "answer is {}".format(ja))
