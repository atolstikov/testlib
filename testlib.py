"""Python port of testlib for contest checkers.

Tested for Yandex.Contest only. This is not a full port of the C++ library:
validators, generators, and interactors are not supported. ``readInt`` and
``readLong`` both accept a signed 64-bit integer; unlike C++ ``readInt``,
values are not narrowed to 32-bit.

A checker calls ``registerTestlibCmd()``, reads ``inf``, ``ouf``, and
``ans``, and finishes with ``quitf()`` or ``quitp()``. Leaving ``main``
without one of those calls exits with FAIL.

Command line::

    checker <input-file> <output-file> <answer-file> [<report-file> [-appes]]

With no report file the message is written to stderr. With a report file
the message is written there instead, in ``cp1251`` (unrepresentable
characters are replaced), matching the C++ library and the ``windows-1251``
declaration of ``-appes`` XML. ``quitp`` rounds the score to two digits
after the decimal, both in the message and in the XML ``points`` attribute.

Files larger than ``MAX_FILE_SIZE`` (128 MiB) are rejected. ``OK`` and
``POINTS`` also reject non-whitespace left in the output file.

Original gist: https://gist.github.com/niyaznigmatullin/211c6aba82ec9825abaa7b8375ce5618
C++ library: https://github.com/MikeMirzayanov/testlib
"""

import atexit
import io
import math
import os
import sys

version = "0.1.2 (Nov 1 2026)"

# Signed 64-bit range, same as C++ std::stoll / readLong.
INT64_MIN = -9223372036854775808
INT64_MAX = 9223372036854775807

# Same default as C++ InStream::maxFileSize.
MAX_FILE_SIZE = 128 * 1024 * 1024

MAX_MESSAGE_LENGTH = 32000

_ARGUMENTS = (
    "Program must be run with the following arguments: "
    "<input-file> <output-file> <answer-file> "
    "[<report-file> [<-appes>]]"
)


class Outcome:
    """Checker verdicts. The numeric values are the process exit codes.

    ``POINTS`` is reported as exit code 0, same as ``OK``. The score itself
    is carried in the message and, in ``-appes`` mode, in the XML attribute.
    """

    OK = 0
    WA = 1
    PE = 2
    FAIL = 3
    POINTS = 5


# Indexed by outcome code. Empty slots keep the C++ TResult numbering:
# 4 dirt (reported as fail), 8 unexpected-eof, 16 partially-correct.
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
    "partially-correct",
]


class FileMode:
    """Which of the three checker files a stream reads."""

    INPUT = 0
    OUTPUT = 1
    ANSWER = 2


LF = 10
CR = 13
TAB = 9
SPACE = ord(" ")
EOFC = -1

# Report path. Empty means "write the message to stderr".
result_name = ""
appes_mode = False

# Score passed to quitp, or None when quitf(POINTS) is used directly.
_quitp_points = None
_quit_depth = 0
_finalize_registered = False
_previous_excepthook = None
_last_exception = None
_in_finalize = False


def halt(exit_code):
    """Exit the process with ``exit_code``. Does not return.

    ``sys.exit`` raised from an ``atexit`` hook is discarded and the
    process can look accepted. The hook path uses ``os._exit`` after
    flushing both standard streams.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, ValueError):
            pass
    if _in_finalize:
        os._exit(exit_code)
    sys.exit(exit_code)


def resultExitCode(result):
    """Map a verdict to a process exit code. Points exits as success."""
    if result == Outcome.POINTS:
        return Outcome.OK
    return result


def shouldCheckDirt(result):
    """True when leftover output tokens must be reported as presentation error."""
    return result == Outcome.OK or result == Outcome.POINTS


def isEof(c):
    return c == EOFC


def isEoln(c):
    return c == LF or c == CR


def isBlanks(c):
    return c == LF or c == CR or c == SPACE or c == TAB


def testlib_part(msg):
    """Shorten ``msg`` to 64 characters, keeping the head and the tail."""
    if len(msg) <= 64:
        return msg
    return msg[:30] + "..." + msg[-31:]


def compress(msg):
    """Alias of ``testlib_part`` used by the sample checkers."""
    return testlib_part(msg)


def englishEnding(x):
    """Return the English ordinal suffix for ``x`` (``st``, ``nd``, ``rd``, or ``th``)."""
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
    """Compare floats by absolute or relative error.

    Finite values compare as ``abs(expected - result) <= max_double_error *
    max(1, abs(expected)) + 1e-15``. NaN matches only NaN. Infinities match
    only an infinity of the same sign.
    """
    if math.isnan(expected):
        return math.isnan(result)
    if math.isinf(expected):
        return math.isinf(result) and (expected > 0) == (result > 0)
    if math.isnan(result) or math.isinf(result):
        return False
    return abs(expected - result) <= max_double_error * max(1, abs(expected)) + 1e-15


class FileReader:
    """Buffered byte reader with a one-character unread stack.

    ``curChar``, ``nextChar``, and ``unreadChar`` use byte values in
    ``0..255``, or ``EOFC`` at end of file.
    """

    def __init__(self, fd, name):
        self.reader = io.BufferedReader(fd)
        self.unread = []
        self.iseof = False
        self.name = name

    def unreadChar(self, c):
        if c != EOFC:
            self.iseof = False
        self.unread.append(c)

    def curChar(self):
        if self.unread:
            return self.unread[-1]
        if self.iseof:
            return EOFC
        got = self.reader.peek(1)
        if len(got) == 0:
            self.iseof = True
            return EOFC
        return got[0]

    def skipChar(self):
        if self.unread:
            self.unread.pop()
            return
        if self.iseof:
            return
        self.reader.read(1)

    def nextChar(self):
        ret = self.curChar()
        self.skipChar()
        return ret

    def close(self):
        self.reader.close()

    def eof(self):
        return self.curChar() == EOFC


class InStream:
    """Byte stream over one checker file.

    Token and number readers skip leading whitespace and abort the checker
    on a malformed token: they do not return in that case. ``readLine``
    does not skip a leading line break. A line break, and every line break
    immediately after it, is consumed, so stacked blank lines collapse.
    """

    def __init__(self):
        self.mode = FileMode.INPUT
        self.reader = None
        self.name = ""
        self.opened = False

    def init(self, filename, mode):
        """Open ``filename`` in binary mode and remember ``mode``."""
        self.name = filename
        self.mode = mode
        if self.opened:
            self.close()
        try:
            fd = io.FileIO(filename, "rb")
        except OSError:
            fd = None
        if fd is None:
            self.opened = False
            self.reader = None
            self._missing_file(filename, mode)
        try:
            fd.seek(0, io.SEEK_END)
            size = fd.tell()
            fd.seek(0)
        except OSError:
            fd.close()
            self.quitf(Outcome.FAIL, "Cannot read file: \"{}\"".format(filename))
        if size > MAX_FILE_SIZE:
            fd.close()
            self.quitf(
                Outcome.PE,
                "File size exceeds {} bytes, size is {}".format(MAX_FILE_SIZE, size),
            )
        self.opened = True
        self.reader = FileReader(fd, filename)

    def _missing_file(self, filename, mode):
        if mode == FileMode.OUTPUT:
            self.quitf(Outcome.PE, "Output file not found: \"{}\"".format(filename))
        if mode == FileMode.ANSWER:
            self.quitf(Outcome.FAIL, "Answer file not found: \"{}\"".format(filename))
        self.quitf(Outcome.FAIL, "Input file not found: \"{}\"".format(filename))

    def close(self):
        """Close the underlying file. Errors on close are ignored."""
        reader = self.reader
        self.reader = None
        self.opened = False
        if reader is None:
            return
        try:
            reader.close()
        except OSError:
            pass

    def _reader(self):
        if self.reader is None:
            self.quitf(Outcome.FAIL, "File is not opened: \"{}\"".format(self.name))
        return self.reader

    def curChar(self):
        """Return the current character without consuming it, or None at EOF."""
        code = self._reader().curChar()
        if code == EOFC:
            return None
        return chr(code)

    def nextChar(self):
        """Consume and return the current character, or None at EOF."""
        code = self._reader().nextChar()
        if code == EOFC:
            return None
        return chr(code)

    def readChar(self, c=None):
        """Read one character. With ``c`` set, that exact character is required."""
        found = self.nextChar()
        if found is None:
            self.quitf(Outcome.PE, "Unexpected end of file - character expected")
        if c is None:
            return found
        if c != found:
            if not isEoln(ord(found)):
                self.quitf(
                    Outcome.PE,
                    "Unexpected character '{}', but '{}' expected".format(found, c),
                )
            else:
                self.quitf(
                    Outcome.PE,
                    "Unexpected character #{}, but '{}' expected".format(ord(found), c),
                )
        return found

    def readSpace(self):
        """Read one required space character."""
        return self.readChar(" ")

    def unreadChar(self, c):
        """Put one character back. ``c`` is a one-character string."""
        if not isinstance(c, str) or len(c) != 1:
            self.quitf(Outcome.FAIL, "unreadChar() expects one character")
        self._reader().unreadChar(ord(c))

    def skipChar(self):
        """Drop the current character, including a character that was unread."""
        self._reader().skipChar()

    def skipBlanks(self):
        """Skip spaces, tabs, CR, and LF."""
        reader = self._reader()
        while isBlanks(reader.curChar()):
            reader.skipChar()

    def seekEof(self):
        """Skip whitespace and return True at end of file.

        A stream that was never opened is treated as already exhausted.
        """
        if self.reader is None:
            return True
        self.skipBlanks()
        return self.reader.eof()

    def readLine(self):
        """Read up to the next line break.

        The result does not contain CR or LF. The first line break and
        every line break immediately after it are consumed, so stacked
        blank lines collapse into the previous read. EOF before any
        character aborts with presentation error.
        """
        reader = self._reader()
        cur = reader.nextChar()
        if cur == EOFC:
            self.quitf(Outcome.PE, "Unexpected end of file - token expected")
        chars = []
        while not (isEoln(cur) or cur == EOFC):
            chars.append(chr(cur))
            cur = reader.nextChar()
        while isEoln(cur):
            cur = reader.nextChar()
        reader.unreadChar(cur)
        return "".join(chars)

    def readWord(self):
        """Read the next token, skipping leading whitespace."""
        reader = self._reader()
        while isBlanks(reader.curChar()):
            reader.skipChar()
        cur = reader.nextChar()
        if cur == EOFC:
            self.quitf(Outcome.PE, "Unexpected end of file - token expected")
        if isBlanks(cur):
            self.quitf(Outcome.FAIL, "Unexpected white-space - token expected")
        chars = []
        while not (isBlanks(cur) or cur == EOFC):
            chars.append(chr(cur))
            cur = reader.nextChar()
        reader.unreadChar(cur)
        if not chars:
            self.quitf(Outcome.PE, "Unexpected end of file or white-space - token expected")
        return "".join(chars)

    def readToken(self):
        """Alias of ``readWord``."""
        return self.readWord()

    def _expected(self, what, buffer):
        self.quitf(Outcome.PE, "Expected {}, but \"{}\" found".format(what, testlib_part(buffer)))

    def stringToInt(self, buffer):
        """Parse a signed 64-bit integer.

        A leading ``+``, a leading minus on zero, and extra zeros (``01``,
        ``00``, ``-0``) are presentation errors. The token may be at most
        20 characters.
        """
        length = len(buffer)
        if length == 0 or length > 20:
            self._expected("integer", buffer)
        minus = length > 1 and buffer[0] == "-"
        retval = 0
        zeroes = 0
        processing_zeroes = True
        for i in range(1 if minus else 0, length):
            ch = buffer[i]
            if ch == "0" and processing_zeroes:
                zeroes += 1
            else:
                processing_zeroes = False
            if ch < "0" or ch > "9":
                self._expected("integer", buffer)
            retval = retval * 10 + ord(ch) - ord("0")
        if (zeroes > 0 and (retval != 0 or minus)) or zeroes > 1:
            self._expected("integer", buffer)
        value = -retval if minus else retval
        if value < INT64_MIN or value > INT64_MAX:
            self._expected("integer", buffer)
        return value

    def stringToFloat(self, buffer):
        """Parse a decimal float in plain or scientific notation.

        Overflow to infinity is preserved. ``nan`` and ``inf`` tokens are
        presentation errors.
        """
        digit_count = 0
        minus_count = 0
        plus_count = 0
        decimal_point_count = 0
        e_count = 0
        for i in range(len(buffer)):
            ch = buffer[i]
            if ("0" <= ch <= "9") or ch == "." or ch == "e" or ch == "E" or ch == "-" or ch == "+":
                if "0" <= ch <= "9":
                    digit_count += 1
                if ch == "e" or ch == "E":
                    e_count += 1
                if ch == "-":
                    minus_count += 1
                if ch == "+":
                    plus_count += 1
                if ch == ".":
                    decimal_point_count += 1
            else:
                self._expected("double", buffer)
        if (
            digit_count == 0
            or minus_count > 2
            or plus_count > 2
            or decimal_point_count > 1
            or e_count > 1
        ):
            self._expected("double", buffer)
        try:
            retval = float(buffer)
        except ValueError:
            self._expected("double", buffer)
        if math.isnan(retval):
            self._expected("double", buffer)
        return retval

    def readInt(self):
        """Read a signed 64-bit integer. See ``stringToInt``."""
        return self.stringToInt(self.readWord())

    def readLong(self):
        """Read a signed 64-bit integer. Same range as ``readInt`` in this port."""
        return self.stringToInt(self.readWord())

    def readFloat(self):
        """Read a floating-point token. See ``stringToFloat``."""
        return self.stringToFloat(self.readWord())

    def readDouble(self):
        """Alias of ``readFloat``."""
        return self.readFloat()

    def eof(self):
        """True at end of file, or when the stream was never opened."""
        if self.reader is None:
            return True
        return self.reader.eof()

    def eoln(self):
        """Return True if the next character starts a line break, and consume it.

        A CR LF pair is one line break. A lone CR is not a line break and
        is put back. EOF counts as a line break. An unopened stream counts
        as a line break too.
        """
        reader = self.reader
        if reader is None:
            return True
        c = reader.nextChar()
        if c == EOFC:
            return True
        if c == CR:
            c2 = reader.nextChar()
            if c2 != LF:
                reader.unreadChar(c2)
                reader.unreadChar(CR)
                return False
            return True
        if c == LF:
            return True
        reader.unreadChar(c)
        return False

    def quitf(self, result, msg):
        """Finish the checker with ``result`` and ``msg``. Does not return.

        A verdict other than FAIL raised while reading the input or the
        answer is rewritten to FAIL: those files are the jury's, so a
        malformed token there is a checker or test error, not a
        participant's presentation error.

        ``OK`` and ``POINTS`` require that the output has no further
        tokens. The message is truncated to ``MAX_MESSAGE_LENGTH``.
        """
        global _quit_depth
        if finalizer is not None and finalizer.alive:
            finalizer.quit_count += 1
        _quit_depth += 1
        if _quit_depth > 5:
            halt(Outcome.FAIL)

        if not isinstance(result, int) or isinstance(result, bool):
            result = Outcome.FAIL
            msg = "quitf() result code must be an integer"
        if not isinstance(msg, str):
            result = Outcome.FAIL
            msg = "quitf() message must be a string"

        if len(msg) > MAX_MESSAGE_LENGTH:
            warn = "message length exceeds {}, the message is truncated: ".format(
                MAX_MESSAGE_LENGTH
            )
            keep = MAX_MESSAGE_LENGTH - len(warn)
            if keep < 0:
                msg = msg[:MAX_MESSAGE_LENGTH]
            else:
                msg = warn + msg[:keep]

        if self.mode != FileMode.OUTPUT and result != Outcome.FAIL:
            self.quitf(Outcome.FAIL, "{} ({})".format(msg, self.name))

        if result == Outcome.POINTS and _quitp_points is None:
            quitf(Outcome.FAIL, "Expected points, but infinity found")

        if shouldCheckDirt(result):
            if not ouf.seekEof():
                quitf(Outcome.PE, "Extra information in the output file")

        if result == Outcome.OK:
            error_name = "ok "
        elif result == Outcome.WA:
            error_name = "wrong-answer "
        elif result == Outcome.PE:
            error_name = "wrong output format "
        elif result == Outcome.POINTS:
            error_name = "points "
        elif result == Outcome.FAIL:
            error_name = "FAIL "
        else:
            quitf(Outcome.FAIL, "WHAT IS THE CODE ??? result code = {}".format(result))

        self.quitscr(0, error_name)
        self._write_result(result, msg)
        self.quitscr(0, msg + "\n")
        inf.close()
        ouf.close()
        ans.close()
        halt(resultExitCode(result))

    def _write_result(self, result, msg):
        global result_name
        if result_name == "":
            return
        try:
            with open(result_name, "w", encoding="cp1251", errors="replace") as result_file:
                if appes_mode:
                    result_file.write("<?xml version=\"1.0\" encoding=\"windows-1251\"?>")
                    if result == Outcome.POINTS:
                        result_file.write(
                            "<result outcome = \"{}\" points = \"{:.2f}\">".format(
                                outcomes[result], _quitp_points
                            )
                        )
                    else:
                        result_file.write("<result outcome = \"{}\">".format(outcomes[result]))
                    self.xmlSafeWrite(result_file, msg)
                    result_file.write("</result>\n")
                else:
                    result_file.write(msg)
        except OSError:
            result_name = ""
            quitf(Outcome.FAIL, "Can not write to the result file")

    @staticmethod
    def quitscr(color, msg):
        """Write ``msg`` to stderr when no report file is used.

        ``color`` is accepted for compatibility with the C++ signature and
        is ignored. A character the stderr encoding cannot represent is
        replaced, so a verdict is not lost on a console encoding error.
        """
        del color
        if result_name != "":
            return
        try:
            sys.stderr.write(msg)
        except UnicodeEncodeError:
            encoding = sys.stderr.encoding or "ascii"
            sys.stderr.buffer.write(msg.encode(encoding, errors="replace"))

    @staticmethod
    def xmlSafeWrite(f, msg):
        """Write ``msg`` as XML text. ``&``, ``<``, ``>``, and quotes are escaped.

        Bytes 0..31 are written as ``.``.
        """
        for ch in msg:
            if ch == "&":
                f.write("&amp;")
            elif ch == "<":
                f.write("&lt;")
            elif ch == ">":
                f.write("&gt;")
            elif ch == '"':
                f.write("&quot;")
            elif 0 <= ord(ch) <= 31:
                f.write(".")
            else:
                f.write(ch)


def quitf(result, msg):
    """Finish the checker by calling ``ouf.quitf``. Does not return."""
    ouf.quitf(result, msg)


def quitp(points, msg):
    """Finish with a partial score. Does not return.

    The report text is ``"{:.2f} {:s}".format(points, msg)``. ``points``
    must be a finite number and must not be negative. This is the only
    supported way to report ``Outcome.POINTS``.
    """
    global _quitp_points
    if isinstance(points, bool) or not isinstance(points, (int, float)):
        quitf(Outcome.FAIL, "Parameter 'points' must be a real number")
    if math.isnan(points):
        quitf(Outcome.FAIL, "Parameter 'points' can't be nan")
    if math.isinf(points):
        quitf(Outcome.FAIL, "Parameter 'points' can't be infinite")
    if points < -1e-8:
        quitf(Outcome.FAIL, "Parameter 'points' can't be negative")
    if points <= 0.0:
        points = 0.0
    _quitp_points = points
    quitf(Outcome.POINTS, "{:.2f} {:s}".format(points, msg))


inf = InStream()
ouf = InStream()
ans = InStream()


class TestlibFinalizeGuard:
    """Exit with FAIL when a registered checker returns without ``quitf``."""

    def __init__(self):
        self.quit_count = 0
        self.alive = True

    def finalize(self):
        cur_alive = self.alive
        self.alive = False
        if not (cur_alive and self.quit_count == 0):
            return
        if _last_exception is not None:
            detail = "{}: {}".format(type(_last_exception).__name__, _last_exception)
            quitf(Outcome.FAIL, "Checker must end with quit call: {}".format(testlib_part(detail)))
        quitf(Outcome.FAIL, "Checker must end with quit call")


finalizer = TestlibFinalizeGuard()


def finalize():
    global _in_finalize
    _in_finalize = True
    finalizer.finalize()


def _excepthook(exc_type, exc, tb):
    global _last_exception
    if exc_type is not None and not issubclass(exc_type, (SystemExit, KeyboardInterrupt)):
        _last_exception = exc
    if _previous_excepthook is not None:
        _previous_excepthook(exc_type, exc, tb)


def _install_hooks():
    global _finalize_registered, _previous_excepthook
    if _previous_excepthook is None:
        _previous_excepthook = sys.excepthook
        sys.excepthook = _excepthook
    if not _finalize_registered:
        atexit.register(finalize)
        _finalize_registered = True


def registerTestlibCmd():
    """Open the checker files from ``sys.argv`` and arm the exit guard.

    See the module docstring for the command line. ``--help`` exits with
    FAIL and the argument contract.
    """
    global result_name, appes_mode, _quitp_points, _last_exception
    _quitp_points = None
    _last_exception = None
    if "--help" in sys.argv:
        quitf(Outcome.FAIL, _ARGUMENTS + "\nhttps://github.com/atolstikov/testlib")
    argc = len(sys.argv)
    if argc < 4 or argc > 6:
        quitf(
            Outcome.FAIL,
            _ARGUMENTS + "\nUse \"--help\" to get help information",
        )
    if argc == 4:
        result_name = ""
        appes_mode = False
    elif argc == 5:
        result_name = sys.argv[4]
        appes_mode = False
    else:
        if sys.argv[5].lower() != "-appes":
            quitf(Outcome.FAIL, _ARGUMENTS)
        result_name = sys.argv[4]
        appes_mode = True
    _install_hooks()
    inf.init(sys.argv[1], FileMode.INPUT)
    ouf.init(sys.argv[2], FileMode.OUTPUT)
    ans.init(sys.argv[3], FileMode.ANSWER)
