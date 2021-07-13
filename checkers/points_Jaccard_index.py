#!/usr/bin/python3

from testlib import *

if __name__ == '__main__':
    """
    Checker with points
    Answer scored to the size of the intersection divided by the size of the union of the sets of options, 
    checked by used and correct choices. More info: https://en.wikipedia.org/wiki/Jaccard_index
    
    This checker can be used for single choice questions. If correct option is unchecked the result will be zero.
    """

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
