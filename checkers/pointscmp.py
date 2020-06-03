#!/usr/bin/python3

from testlib import *


if __name__ == '__main__':
    """
    example of scored checker
    user's output scored to |ja - pa| points
    """
    registerTestlibCmd()

    ja = ans.readDouble()
    pa = ouf.readDouble()

    quitp(abs(ja - pa), "ja={:.4f} pa={:.4f}".format(ja, pa))
