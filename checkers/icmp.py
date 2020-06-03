#!/usr/bin/python3

from testlib import *


if __name__ == '__main__':
    """
    compares two signed integers
    """
    registerTestlibCmd()
    ja = ans.readInt()
    pa = ouf.readInt()
    if ja != pa:
        quitf(Outcome.WA, "expected {}, found {}".format(ja, pa))
    quitf(Outcome.OK, "answer is {}".format(ja))
