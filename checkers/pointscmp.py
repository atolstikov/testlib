#!/usr/bin/python3
"""Score the output by the absolute difference of two doubles.

The score is ``|ja - pa|``.
"""

from testlib import *


if __name__ == '__main__':
    registerTestlibCmd()

    ja = ans.readDouble()
    pa = ouf.readDouble()

    quitp(abs(ja - pa), "ja={:.4f} pa={:.4f}".format(ja, pa))
