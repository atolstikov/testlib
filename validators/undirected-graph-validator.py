#!/usr/bin/python3
"""Validate an undirected graph without loops or multiple edges."""

import sys

from testlib import *


if __name__ == "__main__":
    registerValidation(sys.argv)
    n = inf.readInt(1, 1000, "n")
    inf.readSpace()
    m = inf.readInt(0, 100000, "m")
    inf.readEoln()

    edges = set()
    for _ in range(m):
        a = inf.readInt(1, n, "a_i")
        inf.readSpace()
        b = inf.readInt(1, n, "b_i")
        inf.readEoln()

        ensuref(a != b, "Graph can't contain loops")
        ensuref((a, b) not in edges, "Graph can't contain multiple edges between a pair of vertices")

        edges.add((a, b))
        edges.add((b, a))

    inf.readEof()
