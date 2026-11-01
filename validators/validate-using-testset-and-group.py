#!/usr/bin/python3
"""Validate n and m using the testset limits and the even-n-and-m group."""

import sys

from testlib import *


if __name__ == "__main__":
    registerValidation(sys.argv)

    if validator.testset() == "pretests":
        n = inf.readInt(1, 10, "n")
        inf.readSpace()
        m = inf.readInt(1, 10, "m")
    else:
        n = inf.readInt(1, 100, "n")
        inf.readSpace()
        m = inf.readInt(1, 100, "m")

    if validator.group() == "even-n-and-m":
        ensure(n % 2 == 0, "n % 2 == 0")
        ensure(m % 2 == 0, "m % 2 == 0")

    inf.readEoln()
    inf.readEof()
