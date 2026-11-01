#!/usr/bin/python3
"""Score 1/N points for each correctly checked or correctly unchecked option.

N is the number of options in the input.
"""

from testlib import *

if __name__ == '__main__':
    registerTestlibCmd()

    options = set()
    while not inf.seekEof():
        options.add(inf.readInt())

    correct = set()
    while not ans.seekEof():
        correct.add(ans.readInt())

    checked_by_user = set()
    while not ouf.seekEof():
        checked_by_user.add(ouf.readInt())

    if not options:
        quitf(Outcome.FAIL, "Input contains no options")
    outside = correct - options
    if outside:
        quitf(Outcome.FAIL, "Answer contains numbers that are not in the input: {}".format(sorted(outside)))

    checked_correct = correct & checked_by_user
    unchecked_correct = (options - correct) & (options - checked_by_user)

    quitp((len(checked_correct) + len(unchecked_correct)) / len(options),
          "ja={} pa={} checked_correct={} unchecked_correct={}".
          format(correct, checked_by_user, checked_correct, unchecked_correct))
