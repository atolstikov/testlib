#!/usr/bin/python3
"""Score the answer by the Jaccard index of the chosen and correct options.

The score is the size of the intersection divided by the size of the union.
See https://en.wikipedia.org/wiki/Jaccard_index. For a single-choice question,
an unchecked correct option yields zero.
"""

from testlib import *

if __name__ == '__main__':
    registerTestlibCmd()

    correct = set()
    while not ans.seekEof():
        correct.add(ans.readInt())

    checked_by_user = set()
    while not ouf.seekEof():
        checked_by_user.add(ouf.readInt())

    checked_correct = correct & checked_by_user
    correct_and_wrong_checked = correct | checked_by_user

    quitp(len(checked_correct) / len(correct_and_wrong_checked) if correct_and_wrong_checked else 1.0,
          "correct={} checked_by_user={} checked_correct={} correct_and_wrong_checked={}".
          format(correct, checked_by_user, checked_correct, correct_and_wrong_checked))
