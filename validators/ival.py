#!/usr/bin/python3
"""Validate a single integer n in [1, 100], then a line break and EOF."""

import sys

from testlib import *


if __name__ == "__main__":
    registerValidation(sys.argv)
    inf.readInt(1, 100, "n")
    inf.readEoln()
    inf.readEof()
