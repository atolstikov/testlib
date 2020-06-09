"""
Python version of testlib, the library for creating checkers only.

This version in tested for Yandex.Contest only.

The original source of this library here (https://gist.github.com/niyaznigmatullin/211c6aba82ec9825abaa7b8375ce5618).
"""

import io
import atexit
import math
import sys

version = "0.1.0 (Jun 4 2020)"


class Outcome:
    OK = 0
    WA = 1
    PE = 2
    FAIL = 3


outcomes = [
    "accepted",
    "wrong-answer",
    "presentation-error",
    "fail",
    "fail",
    "points",
    "reserved",
    "reserved",
    "unexpected-eof",
    "reserved",
    "reserved",
    "reserved",
    "reserved",
    "reserved",
    "reserved",
    "reserved",
    "partially-correct"
]


class FileMode:
    INPUT = 0
    OUTPUT = 1
    ANSWER = 2


LF = 10
CR = 13
TAB = 9
SPACE = ord(' ')
EOFC = -1

MAX_MESSAGE_LENGTH = 32000


def halt(exit_code):
    sys.exit(exit_code)


def resultExitCode(result):
    return result


def shouldCheckDirt(result):
    return result == Outcome.OK


def isEof(c):
    return c == EOFC


def isEoln(c):
    return c == LF or c == CR


def isBlanks(c):
    return c == LF or c == CR or c == SPACE or c == TAB


def testlib_part(msg):
    if len(msg) <= 64:
        return msg
    return msg[:30] + "..." + msg[-31:]


def compress(msg):
    return testlib_part(msg)


def englishEnding(x):
    x %= 100
    if x // 10 == 1:
        return "th"
    if x % 10 == 1:
        return "st"
    if x % 10 == 2:
        return "nd"
    if x % 10 == 3:
        return "rd"
    return "th"


def doubleCompare(expected, result, max_double_error):
    """
    Compares double values for relative or absolute error.
    :param expected: expected correct value
    :param result: test value
    :param max_double_error: maximal error
    :return: Is |expected - result| <= max_double_error * max(1, |expected|)
    """
    return abs(expected - result) <= max_double_error * max(1, abs(expected)) + 1E-15


class InStream:

    def __init__(self):
        self.mode = FileMode.INPUT
        self.reader = None
        self.name = ''
        self.opened = False

    def init(self, filename, mode):
        self.name = filename
        self.mode = mode
        if self.opened:
            self.close()
        try:
            fd = io.FileIO(filename, 'rb')
        except IOError:
            fd = None
        if fd is None:
            self.opened = False
            self.reader = None
        else:
            self.opened = True
            self.reader = FileReader(fd, filename)

    def close(self):
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        self.opened = False

    def curChar(self):
        return chr(self.reader.curChar())

    def nextChar(self):
        return chr(self.reader.nextChar())

    def readChar(self, c=None):
        if c is None:
            return self.nextChar()
        else:
            found = self.readChar()
            if c != found:
                if not isEoln(found):
                    self.quitf(Outcome.PE, "Unexpected character '{}', but '{}' expected".format(found, c))
                else:
                    self.quitf(Outcome.PE, "Unexpected character #{}, but '{}' expected".format(ord(found), c))
            return found

    def readSpace(self):
        return self.readChar(' ')

    def unreadChar(self, c):
        return self.reader.unreadChar(ord(c))

    def skipChar(self):
        self.reader.skipChar()

    def skipBlanks(self):
        while isBlanks(self.reader.curChar()):
            self.reader.skipChar()

    def seekEof(self):
        self.skipBlanks()
        return self.reader.eof()

    def readWord(self):
        self.skipBlanks()
        cur = self.reader.nextChar()
        if cur == EOFC:
            self.quitf(Outcome.PE, "Unexpected end of file - token expected")

        if isBlanks(cur):
            self.quitf(Outcome.FAIL, "Unexpected white-space - token expected")

        result = ''
        while not (isBlanks(cur) or cur == EOFC):
            result += chr(cur)
            cur = self.reader.nextChar()
        self.reader.unreadChar(cur)
        if result == '':
            self.quitf(Outcome.PE, "Unexpected end of file or white-space - token expected")
        return result

    def readToken(self):
        return self.readWord()

    def stringToInt(self, buffer):
        minus = False
        length = len(buffer)
        if length > 1 and buffer[0] == '-':
            minus = True
        if length > 20:
            self.quitf(Outcome.PE, "Expected integer, but \"{}}\" found".format(testlib_part(buffer)))
        retval = 0
        zeroes = 0
        processing_zeroes = True
        for i in range(1 if minus else 0, length):
            if buffer[i] == '0' and processing_zeroes:
                zeroes += 1
            else:
                processing_zeroes = False
            if buffer[i] < '0' or buffer[i] > '9':
                self.quitf(Outcome.PE, "Expected integer, but \"{}\" found".format(testlib_part(buffer)))
            retval = retval * 10 + ord(buffer[i]) - ord('0')
        if (zeroes > 0 and (retval != 0 or minus)) or zeroes > 1:
            self.quitf(Outcome.PE, "Expected integer, but \"{}\" found".format(testlib_part(buffer)))
        return -retval if minus else retval

    def stringToFloat(self, buffer):
        digit_count = 0
        minus_count = 0
        plus_count = 0
        decimal_point_count = 0
        e_count = 0
        retval = 0
        for i in range(len(buffer)):
            if ('0' <= buffer[i] <= '9') or buffer[i] == '.' or buffer[i] == 'e' or buffer[i] == 'E' or \
                    buffer[i] == '-' or buffer[i] == '+':
                if '0' <= buffer[i] <= '9':
                    digit_count += 1
                if buffer[i] == 'e' or buffer[i] == 'E':
                    e_count += 1
                if buffer[i] == '-':
                    minus_count += 1
                if buffer[i] == '+':
                    plus_count += 1
                if buffer[i] == '.':
                    decimal_point_count += 1
            else:
                self.quitf(Outcome.PE, "Expected float, but \"{}\" found".format(testlib_part(buffer)))
        if digit_count == 0 or minus_count > 2 or plus_count > 2 or decimal_point_count > 1 or e_count > 1:
            self.quitf(Outcome.PE, "Expected integer, but \"{}\" found".format(testlib_part(buffer)))
        try:
            retval = float(buffer)
            if math.isnan(retval):
                self.quitf(Outcome.PE, "Expected integer, but \"{}\" found".format(testlib_part(buffer)))
        except ValueError:
            self.quitf(Outcome.PE, "Expected integer, but \"{}\" found".format(testlib_part(buffer)))
        return retval

    def readInt(self):
        return self.stringToInt(self.readWord())

    def readLong(self):
        return self.stringToInt(self.readWord())

    def readFloat(self):
        return self.stringToFloat(self.readWord())

    def readDouble(self):
        return self.readFloat()

    def quitf(self, result, msg):
        if finalizer is not None:
            if finalizer.alive is not None:
                if finalizer.alive:
                    finalizer.quit_count += 1
        if len(msg) > MAX_MESSAGE_LENGTH:
            warn = "message length exceeds {}, the message is truncated: ".format(MAX_MESSAGE_LENGTH)
            msg = warn + msg[:MAX_MESSAGE_LENGTH - len(warn)]
        if self.mode != FileMode.OUTPUT and result != Outcome.FAIL:
            self.quitf(Outcome.FAIL, "{} ({})".format(msg, self.name))
        if shouldCheckDirt(result):
            if not ouf.seekEof():
                quitf(Outcome.PE, "Extra information in the output file")
        if result == Outcome.OK:
            error_name = 'ok '
            self.quitscr(0, error_name)
        elif result == Outcome.WA:
            error_name = 'wrong-answer '
            self.quitscr(0, error_name)
        elif result == Outcome.PE:
            error_name = "wrong output format "
            self.quitscr(0, error_name)
        elif result == Outcome.FAIL:
            error_name = "FAIL "
            self.quitscr(0, error_name)
        else:
            quitf(Outcome.FAIL, "WHAT IS THE CODE ??? result code = {}".format(result))

        if result_name != "":
            try:
                result_file = open(result_name, "w")
                if appes_mode:
                    result_file.write("<?xml version=\"1.0\" encoding=\"windows-1251\"?>")
                    result_file.write("<result outcome = \"{}\">".format(outcomes[result]))
                    self.xmlSafeWrite(result_file, msg)
                    result_file.write("</result>\n")
                else:
                    result_file.write(msg)
                result_file.close()
            except IOError:
                quitf(Outcome.FAIL, "Can not write to the result file")
        self.quitscr(0, msg + '\n')
        inf.close()
        ouf.close()
        ans.close()
        halt(resultExitCode(result))

    @staticmethod
    def quitscr(color, msg):
        assert color == 0  # unused parameter of color in console
        if result_name == "":
            print(msg, file=sys.stderr, end='')

    @staticmethod
    def xmlSafeWrite(f, msg):
        for i in range(len(msg)):
            if msg[i] == '&':
                f.write('&amp;')
                continue
            if msg[i] == '<':
                f.write('&lt;')
                continue
            if msg[i] == '>':
                f.write('&gt;')
                continue
            if msg[i] == '"':
                f.write('&quot;')
                continue
            if 0 <= ord(msg[i]) <= 31:
                f.write('.')
                continue
            f.write(msg[i])


class FileReader:
    def __init__(self, fd, name):
        self.reader = io.BufferedReader(fd)
        self.unread = []
        self.iseof = False
        self.name = name

    def unreadChar(self, c):
        self.unread.append(c)

    def curChar(self):
        if self.iseof:
            return -1
        if len(self.unread) > 0:
            return self.unread[-1]
        else:
            got = self.reader.peek(1)
            if len(got) == 0:
                self.iseof = True
                return -1
            return got[0]

    def skipChar(self):
        if self.iseof:
            return
        if len(self.unread) > 0:
            self.unread.pop()
        else:
            self.reader.read(1)

    def nextChar(self):
        ret = self.curChar()
        self.skipChar()
        return ret

    def close(self):
        self.reader.close()

    def eof(self):
        return self.iseof


def quitf(result, msg):
    ouf.quitf(result, msg)


def quitp(points, msg):
    quit_message = '{:.2f} {:s}'.format(points, msg)
    quitf(Outcome.OK, quit_message)


inf = InStream()
ouf = InStream()
ans = InStream()
result_name = ""
appes_mode = False


class TestlibFinalizeGuard:
    def __init__(self):
        self.quit_count = 0
        self.alive = True
        self.copyOuf = ouf

    def finalize(self):
        cur_alive = self.alive
        self.alive = False
        if cur_alive and self.quit_count == 0:
            quitf(Outcome.FAIL, "Checker must end with quit call")


finalizer = TestlibFinalizeGuard()


def finalize():
    finalizer.finalize()


def registerTestlibCmd():
    global result_name, appes_mode
    argc = len(sys.argv)
    if "--help" in sys.argv:
        raise Exception('https://github.com/atolstikov/testlib')
        # testlib_help()
    if argc < 4 or argc > 6:
        quitf(Outcome.FAIL,
              "Program must be run with the following arguments: "
              "<input-file> <output-file> <answer-file> "
              "[<report-file> [<-appes>]]\nUse \"--help\" to get help information")
    if argc == 4:
        result_name = ""
        appes_mode = False
    if argc == 5:
        result_name = sys.argv[4]
        appes_mode = False
    if argc == 6:
        if sys.argv[5].lower() != "-appes":
            quitf(Outcome.FAIL,
                  "Program must be run with the following arguments: "
                  "<input-file> <output-file> <answer-file> [<report-file> [<-appes>]]")
        else:
            result_name = sys.argv[4]
            appes_mode = True
    inf.init(sys.argv[1], FileMode.INPUT)
    ouf.init(sys.argv[2], FileMode.OUTPUT)
    ans.init(sys.argv[3], FileMode.ANSWER)
    atexit.register(finalize)
