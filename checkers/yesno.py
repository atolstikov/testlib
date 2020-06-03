#!/usr/bin/python3

from testlib import *

YES = "YES"
NO = "NO"


if __name__ == '__main__':
    """
    YES or NO (case insensitive) checker 
    """

    registerTestlibCmd()

    jury_answer = ans.readWord().upper()
    participant_answer = ouf.readWord().upper()

    if jury_answer != YES and jury_answer != NO:
        quitf(Outcome.FAIL, "{} or {} expected in answer, but {} found".format(YES, NO, compress(jury_answer)))

    if participant_answer != YES and participant_answer != NO:
        quitf(Outcome.PE, "{} or {} expected, but {} found".format(YES, NO, compress(participant_answer)))

    if jury_answer != participant_answer:
        quitf(Outcome.WA, "expected {}, found {}".format(compress(jury_answer), compress(participant_answer)))

    quitf(Outcome.OK, "answer is {}".format(participant_answer))
