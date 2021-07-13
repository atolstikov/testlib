#!/usr/bin/python3

from testlib import *

if __name__ == '__main__':
    """
    Checker with points
    Answer scored to 1.0/options points for each correct choice (correctly checked and unchecked).
    """
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

    checked_correct = correct & checked_by_user
    unchecked_correct = (options - correct) & (options - checked_by_user)

    quitp((len(checked_correct) + len(unchecked_correct)) / len(options),
          "ja={} pa={} checked_correct={} unchecked_correct={}".
          format(correct, checked_by_user, checked_correct, unchecked_correct))
