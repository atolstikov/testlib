#!/usr/bin/python3
"""Validate n in [1, 100000] and n signed integers in [-10^15, 10^15]."""

import sys

from testlib import *


if __name__ == "__main__":
    registerValidation(sys.argv)
    n = inf.readInt(1, 100000, "n")
    inf.readEoln()
    inf.readLongs(n, -1000000000 * 1000000, 1000000000 * 1000000, "a")
    inf.readEoln()
    inf.readEof()
