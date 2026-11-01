#!/usr/bin/python3
"""Validate one token of 1..100 lowercase latin letters."""

import sys

from testlib import *


if __name__ == "__main__":
    registerValidation(sys.argv)
    inf.readToken("[a-z]{1,100}", "s")
    inf.readEoln()
    inf.readEof()
