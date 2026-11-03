"""Python port of testlib for contest checkers and validators.

Tested for Yandex.Contest only. Generators and interactors are not supported.
``readInt`` is a signed 32-bit integer and ``readLong`` is a signed 64-bit
integer, as in the C++ library. ``registerValidation`` reads stdin strictly.
A validator read error includes the line number. ``ensuref`` reports a
failed condition, and ``validator.testset`` and ``validator.group`` come
from the command line.

A checker calls ``registerTestlibCmd()``, reads ``inf``, ``ouf``, and
``ans``, and finishes with ``quitf()`` or ``quitp()``. Leaving ``main``
without one of those calls exits with FAIL.

Command line::

    checker <input-file> <output-file> <answer-file> [<report-file> [-appes]]

With no report file the message is written to stderr. With a report file
the message is written there instead, in ``cp1251`` (unrepresentable
characters are replaced), matching the C++ library and the ``windows-1251``
declaration of ``-appes`` XML. ``quitp`` formats the score like C++
``%.10f`` with trailing zeros removed, and rejects a score above 1e6.
The XML ``points`` attribute uses that same text.

Files larger than ``MAX_FILE_SIZE`` (128 MiB) are rejected. ``OK`` and
``POINTS`` also reject non-whitespace left in the output file.

Original gist: https://gist.github.com/niyaznigmatullin/211c6aba82ec9825abaa7b8375ce5618
C++ library: https://github.com/MikeMirzayanov/testlib
"""

import atexit
import bisect
import io
import math
import os
import sys

version = "0.3.0 (Nov 3 2026)"

# Signed 32-bit range, same as C++ readInt / readInteger.
INT32_MIN = -2147483648
INT32_MAX = 2147483647

# Signed 64-bit range, same as C++ std::stoll / readLong.
INT64_MIN = -9223372036854775808
INT64_MAX = 9223372036854775807
UINT64_MAX = 18446744073709551615

# Same default as C++ InStream::maxFileSize.
MAX_FILE_SIZE = 128 * 1024 * 1024
MAX_TOKEN_LENGTH = 32 * 1024 * 1024

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
_read_many_index = None
testlib_mode = "checker"


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

    Match C++ testlib's absolute or relative tolerance. Values with an
    absolute magnitude above 1e300 are treated as infinite by testlib.
    """
    max_double_error += 1e-15
    if math.isnan(expected):
        return math.isnan(result)
    if abs(expected) > 1e300:
        return abs(result) > 1e300 and (expected > 0) == (result > 0)
    if math.isnan(result) or abs(result) > 1e300:
        return False
    if abs(result - expected) <= max_double_error:
        return True
    lower = min(expected * (1.0 - max_double_error), expected * (1.0 + max_double_error))
    upper = max(expected * (1.0 - max_double_error), expected * (1.0 + max_double_error))
    return lower <= result <= upper


def _human_int(value):
    if value == 0:
        return "0"
    reduced = value
    trailing = 0
    while reduced % 10 == 0:
        reduced //= 10
        trailing += 1
    if trailing >= 7:
        if reduced == 1:
            return "10^{}".format(trailing)
        if reduced == -1:
            return "-10^{}".format(trailing)
        return "{}*10^{}".format(reduced, trailing)
    return str(value)


def _human_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        quitf(Outcome.FAIL, "Bounds must be numbers.")
    if isinstance(value, int):
        return _human_int(value)
    return str(value)


def _bounds_given(minv, maxv):
    if minv is None and maxv is None:
        return False
    if minv is None or maxv is None:
        quitf(Outcome.FAIL, "Both minv and maxv are required.")
    return True


def _remove_double_trailing_zeroes(value):
    while value and value[-1] == "0" and "." in value:
        value = value[:-1]
    if value and value[-1] == ".":
        return value + "0"
    return value


def _format_points(points):
    return _remove_double_trailing_zeroes("{:.10f}".format(points))


def _prepare_points(points):
    if math.isnan(points):
        quitf(Outcome.FAIL, "Parameter 'points' can't be nan")
    if math.isinf(points):
        quitf(Outcome.FAIL, "Parameter 'points' can't be infinite")
    if points < -1e-8:
        quitf(Outcome.FAIL, "Parameter 'points' can't be negative")
    if points <= 0.0:
        points = 0.0
    if points > 1e6 + 1e-8:
        quitf(Outcome.FAIL, "Parameter 'points' can't be greater than 1E6")
    if points >= 1e6:
        points = 1e6
    return points


def _pattern_is_command(source, pos, value):
    if pos >= len(source):
        return False
    slashes = 0
    before = pos - 1
    while before >= 0 and source[before] == "\\":
        before -= 1
        slashes += 1
    return slashes % 2 == 0 and source[pos] == value


def _pattern_get_char(source, pos):
    if pos >= len(source):
        quitf(Outcome.FAIL, 'pattern: Illegal pattern (or part) "{}"'.format(source))
    if pos < len(source) and source[pos] == "\\" and pos + 1 < len(source):
        return source[pos + 1], pos + 2
    if source[pos] == "\\" and pos + 1 >= len(source):
        quitf(Outcome.FAIL, 'pattern: Illegal pattern (or part) "{}"'.format(source))
    return source[pos], pos + 1


def _pattern_parse_count(part):
    index = 0
    if part and part[0] in "+-":
        index = 1
    start = index
    while index < len(part) and part[index].isdigit():
        index += 1
    if index == start:
        return None
    return int(part[:index])


def _pattern_scan_counts(source, pos):
    if pos >= len(source):
        return 1, 1, pos
    if _pattern_is_command(source, pos, "{"):
        parts = []
        part = ""
        pos += 1
        while pos < len(source) and not _pattern_is_command(source, pos, "}"):
            if _pattern_is_command(source, pos, ","):
                parts.append(part)
                part = ""
                pos += 1
            else:
                char, pos = _pattern_get_char(source, pos)
                part += char
        if part != "":
            parts.append(part)
        if not _pattern_is_command(source, pos, "}"):
            quitf(Outcome.FAIL, 'pattern: Illegal pattern (or part) "{}"'.format(source))
        pos += 1
        if len(parts) < 1 or len(parts) > 2:
            quitf(Outcome.FAIL, 'pattern: Illegal pattern (or part) "{}"'.format(source))
        numbers = []
        for item in parts:
            if item == "":
                quitf(Outcome.FAIL, 'pattern: Illegal pattern (or part) "{}"'.format(source))
            number = _pattern_parse_count(item)
            if number is None:
                quitf(Outcome.FAIL, 'pattern: Illegal pattern (or part) "{}"'.format(source))
            numbers.append(number)
        if len(numbers) == 1:
            from_count = to_count = numbers[0]
        else:
            from_count = numbers[0]
            to_count = numbers[1]
        if from_count > to_count:
            quitf(Outcome.FAIL, 'pattern: Illegal pattern (or part) "{}"'.format(source))
        return from_count, to_count, pos
    if _pattern_is_command(source, pos, "?"):
        return 0, 1, pos + 1
    if _pattern_is_command(source, pos, "*"):
        return 0, INT32_MAX, pos + 1
    if _pattern_is_command(source, pos, "+"):
        return 1, INT32_MAX, pos + 1
    return 1, 1, pos


def _pattern_greedy(text, pos, chars):
    result = 0
    while pos < len(text):
        char = text[pos]
        pos += 1
        index = bisect.bisect_left(chars, char)
        if index == len(chars) or chars[index] != char:
            break
        result += 1
    return result


def _pattern_scan_char_set(source, pos):
    if pos >= len(source):
        quitf(Outcome.FAIL, 'pattern: Illegal pattern (or part) "{}"'.format(source))
    result = []
    if _pattern_is_command(source, pos, "["):
        pos += 1
        negative = _pattern_is_command(source, pos, "^")
        if negative:
            pos += 1
        prev = None
        while pos < len(source) and not _pattern_is_command(source, pos, "]"):
            if _pattern_is_command(source, pos, "-") and prev is not None:
                pos += 1
                if pos + 1 == len(source) or _pattern_is_command(source, pos, "]"):
                    result.append(prev)
                    prev = "-"
                    continue
                next_char, pos = _pattern_get_char(source, pos)
                if prev > next_char:
                    quitf(Outcome.FAIL, 'pattern: Illegal pattern (or part) "{}"'.format(source))
                code = ord(prev)
                last = ord(next_char)
                while code != last:
                    result.append(chr(code))
                    code += 1
                result.append(next_char)
                prev = None
            else:
                if prev is not None:
                    result.append(prev)
                prev, pos = _pattern_get_char(source, pos)
        if prev is not None:
            result.append(prev)
        if not _pattern_is_command(source, pos, "]"):
            quitf(Outcome.FAIL, 'pattern: Illegal pattern (or part) "{}"'.format(source))
        pos += 1
        if negative:
            result.sort()
            actual = []
            for code in range(255):
                char = chr(code)
                index = bisect.bisect_left(result, char)
                if index == len(result) or result[index] != char:
                    actual.append(char)
            result = actual
        result.sort()
    else:
        char, pos = _pattern_get_char(source, pos)
        result.append(char)
    return result, pos


class Pattern:
    """testlib pattern, not a Python regular expression.

    Character sets ``[a-z]`` and ``[^0-9]``, counts ``{n}`` and ``{n,m}``,
    ``?``, ``*``, ``+``, alternation ``|``, and grouping ``()``. Spaces are
    ignored. A backslash escapes the next character.
    """

    def __init__(self, source):
        self._source = source
        self.from_count = 0
        self.to_count = 0
        self.chars = []
        self.children = []
        stripped = []
        for index in range(len(source)):
            if not _pattern_is_command(source, index, " "):
                stripped.append(source[index])
        source = "".join(stripped)
        opened = 0
        first_close = -1
        seps = []
        for index in range(len(source)):
            if _pattern_is_command(source, index, "("):
                opened += 1
                continue
            if _pattern_is_command(source, index, ")"):
                opened -= 1
                if opened == 0 and first_close == -1:
                    first_close = index
                continue
            if opened < 0:
                quitf(Outcome.FAIL, 'pattern: Illegal pattern (or part) "{}"'.format(source))
            if _pattern_is_command(source, index, "|") and opened == 0:
                seps.append(index)
        if opened != 0:
            quitf(Outcome.FAIL, 'pattern: Illegal pattern (or part) "{}"'.format(source))
        if (
            not seps
            and first_close + 1 == len(source)
            and _pattern_is_command(source, 0, "(")
            and _pattern_is_command(source, len(source) - 1, ")")
        ):
            self.children.append(Pattern(source[1:-1]))
        elif seps:
            seps.append(len(source))
            last = 0
            for sep in seps:
                self.children.append(Pattern(source[last:sep]))
                last = sep + 1
        else:
            pos = 0
            self.chars, pos = _pattern_scan_char_set(source, pos)
            self.from_count, self.to_count, pos = _pattern_scan_counts(source, pos)
            if pos < len(source):
                self.children.append(Pattern(source[pos:]))

    def src(self):
        """Return the pattern text passed to the constructor."""
        return self._source

    def matches(self, text, pos=0):
        """Return True when ``text`` from ``pos`` matches this pattern."""
        if self.to_count > 0:
            size = _pattern_greedy(text, pos, self.chars)
            if size < self.from_count:
                return False
            if size > self.to_count:
                size = self.to_count
            pos += size
        if self.children:
            for child in self.children:
                if child.matches(text, pos):
                    return True
            return False
        return pos == len(text)


class FileReader:
    """Buffered byte reader with a one-character unread stack.

    ``curChar``, ``nextChar``, and ``unreadChar`` use byte values in
    ``0..255``, or ``EOFC`` at end of file.
    """

    def __init__(self, fd, name):
        if isinstance(fd, io.BufferedIOBase):
            self.reader = fd
            self._close_reader = False
        else:
            self.reader = io.BufferedReader(fd)
            self._close_reader = True
        self.unread = []
        self.iseof = False
        self.name = name
        self.line = 1

    def unreadChar(self, c):
        if c == LF:
            self.line -= 1
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
            if self.unread.pop() == LF:
                self.line += 1
            return
        if self.iseof:
            return
        got = self.reader.read(1)
        if got and got[0] == LF:
            self.line += 1

    def nextChar(self):
        ret = self.curChar()
        self.skipChar()
        return ret

    def close(self):
        if self._close_reader:
            self.reader.close()

    def eof(self):
        return self.curChar() == EOFC


class InStream:
    """Byte stream over one checker file, or over stdin for a validator.

    Checker mode skips leading whitespace. Strict mode, used by validators,
    does not. A malformed token aborts and does not return. ``readLine``
    consumes exactly one line break, preserving empty lines. In strict mode
    one platform line break is required.
    """

    def __init__(self):
        self.mode = FileMode.INPUT
        self.reader = None
        self.name = ""
        self.opened = False
        self.strict = False
        self.lastLine = -1
        self.maxTokenLength = MAX_TOKEN_LENGTH

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

    def init_stdin(self):
        """Read standard input in binary mode. The stream is not seeked."""
        self.name = "stdin"
        self.mode = FileMode.INPUT
        if self.opened:
            self.close()
        self.opened = True
        self.reader = FileReader(sys.stdin.buffer, "stdin")

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
        if c is not None and self.reader is not None:
            self.lastLine = self.reader.line
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

    def readLine(self, ptrn=None, variableName=""):
        """Read up to the next line break.

        The result does not contain CR or LF. In checker mode the first
        line break and every line break immediately after it are consumed,
        so stacked blank lines collapse, and EOF before any character is a
        presentation error. In strict mode exactly one platform line break
        is required. ``ptrn`` is a :class:`Pattern` or a pattern string; a
        mismatch is WA.
        """
        if self.strict:
            line = self._read_line_strict()
        else:
            line = self._read_line_checker()
        if ptrn is not None:
            self._check_pattern(line, ptrn, variableName, "Line")
        return line

    def readString(self, ptrn=None, variableName=""):
        """Alias of ``readLine``."""
        return self.readLine(ptrn, variableName)

    def readLines(self, size, ptrn=None, variablesName="", indexBase=1):
        """Read ``size`` lines. In strict mode each line needs its own EOLN."""
        return self._read_many(
            "readLines", size, indexBase,
            lambda: self.readLine(ptrn, variablesName), False,
        )

    def readStrings(self, size, ptrn=None, variablesName="", indexBase=1):
        """Alias of ``readLines``."""
        return self._read_many(
            "readStrings", size, indexBase,
            lambda: self.readString(ptrn, variablesName), False,
        )

    def _read_line_checker(self):
        reader = self._reader()
        chars = []
        while True:
            cur = reader.curChar()
            if cur == LF or cur == EOFC:
                break
            if cur == CR:
                reader.nextChar()
                if reader.curChar() == LF:
                    reader.unreadChar(CR)
                    break
                continue
            chars.append(chr(reader.nextChar()))
        self.eoln()
        return "".join(chars)

    def _read_line_strict(self):
        reader = self._reader()
        chars = []
        while True:
            cur = reader.curChar()
            if cur == LF or cur == EOFC:
                break
            if cur == CR:
                reader.nextChar()
                if reader.curChar() == LF:
                    reader.unreadChar(CR)
                    break
                continue
            chars.append(chr(reader.nextChar()))
        self.readEoln()
        return "".join(chars)

    def readWord(self, ptrn=None, variableName=""):
        """Read the next token.

        Checker mode skips leading whitespace. Strict mode does not, and a
        space where a token is required is a presentation error. ``ptrn``
        is a :class:`Pattern` or a pattern string; a mismatch is WA.
        """
        word = self._read_word()
        if ptrn is not None:
            self._check_pattern(word, ptrn, variableName, "Token")
        return word

    def _read_word(self):
        reader = self._reader()
        if not self.strict:
            while isBlanks(reader.curChar()):
                reader.skipChar()
        self.lastLine = reader.line
        cur = reader.nextChar()
        if cur == EOFC:
            self.quitf(Outcome.PE, "Unexpected end of file - token expected")
        if isBlanks(cur):
            self.quitf(Outcome.PE, "Unexpected white-space - token expected")
        chars = []
        while not (isBlanks(cur) or cur == EOFC):
            chars.append(chr(cur))
            if len(chars) > self.maxTokenLength:
                self.quitf(Outcome.PE, "Length of token exceeds {}, token is '{}...'".format(
                    self.maxTokenLength, testlib_part("".join(chars))))
            cur = reader.nextChar()
        reader.unreadChar(cur)
        if not chars:
            self.quitf(Outcome.PE, "Unexpected end of file or white-space - token expected")
        return "".join(chars)

    def readToken(self, ptrn=None, variableName=""):
        """Alias of ``readWord``."""
        return self.readWord(ptrn, variableName)

    def readWords(self, size, ptrn=None, variablesName="", indexBase=1):
        """Read ``size`` space-separated tokens, optionally matching ``ptrn``."""
        return self._read_many(
            "readWords", size, indexBase,
            lambda: self.readWord(ptrn, variablesName), True,
        )

    def readTokens(self, size, ptrn=None, variablesName="", indexBase=1):
        """Alias of ``readWords``."""
        return self._read_many(
            "readTokens", size, indexBase,
            lambda: self.readToken(ptrn, variablesName), True,
        )

    def readSpace(self):
        """Read one space character."""
        return self.readChar(" ")

    def _check_bounds(self, value, minv, maxv, variable_name, kind):
        if minv <= value <= maxv:
            return
        rendered = _human_number(value)
        bounds = "[{}, {}]".format(_human_number(minv), _human_number(maxv))
        index = _read_many_index
        if index is None:
            if not variable_name:
                message = "{} {} violates the range {}".format(kind, rendered, bounds)
            else:
                message = "{} parameter [name={}] equals to {}, violates the range {}".format(
                    kind, variable_name, rendered, bounds
                )
        elif not variable_name:
            message = "{} element [index={}] equals to {}, violates the range {}".format(
                kind, index, rendered, bounds
            )
        else:
            message = "{} element {}[{}] equals to {}, violates the range {}".format(
                kind, variable_name, index, rendered, bounds
            )
        self.quitf(Outcome.WA, message)

    def _check_pattern(self, text, ptrn, variable_name, kind):
        pattern = ptrn if isinstance(ptrn, Pattern) else Pattern(ptrn)
        if pattern.matches(text):
            return
        shown = testlib_part(text)
        source = pattern.src()
        index = _read_many_index
        if index is None:
            if not variable_name:
                message = '{} "{}" doesn\'t correspond to pattern "{}"'.format(kind, shown, source)
            elif kind == "Line":
                message = 'Line [name={}] equals to "{}", doesn\'t correspond to pattern "{}"'.format(
                    variable_name, shown, source
                )
            else:
                message = 'Token parameter [name={}] equals to "{}", doesn\'t correspond to pattern "{}"'.format(
                    variable_name, shown, source
                )
        elif not variable_name:
            message = '{} element [index={}] equals to "{}" doesn\'t correspond to pattern "{}"'.format(
                kind, index, shown, source
            )
        else:
            message = '{} element {}[{}] equals to "{}", doesn\'t correspond to pattern "{}"'.format(
                kind, variable_name, index, shown, source
            )
        self.quitf(Outcome.WA, message)

    def _read_many(self, name, size, index_base, read_one, space):
        global _read_many_index
        if isinstance(size, bool) or not isinstance(size, int):
            self.quitf(Outcome.FAIL, "{}: size should be an integer.".format(name))
        if size < 0:
            self.quitf(Outcome.FAIL, "{}: size should be non-negative.".format(name))
        if size > 100000000:
            self.quitf(Outcome.FAIL, "{}: size should be at most 100000000.".format(name))
        result = []
        _read_many_index = index_base
        try:
            for i in range(size):
                result.append(read_one())
                _read_many_index += 1
                if self.strict and space and i + 1 < size:
                    self.readSpace()
        finally:
            _read_many_index = None
        return result

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

    def stringToUnsignedLong(self, buffer):
        """Parse a canonical unsigned 64-bit decimal integer."""
        if (
            not buffer or len(buffer) > 20
            or (len(buffer) > 1 and buffer[0] == "0")
            or any(ch < "0" or ch > "9" for ch in buffer)
        ):
            self._expected("unsigned integer", buffer)
        value = int(buffer)
        if value > UINT64_MAX:
            self._expected("unsigned integer", buffer)
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

    def stringToStrictDouble(self, buffer, minAfterPointDigitCount, maxAfterPointDigitCount):
        """Parse a double with no exponent and a fixed fractional length.

        ``-0`` and ``-0.00`` are rejected as redundant minus. A leading
        ``+``, a leading zero (``01``, ``00.1``), and a trailing dot are
        presentation errors.
        """
        if minAfterPointDigitCount < 0:
            self.quitf(
                Outcome.FAIL,
                "stringToStrictDouble: minAfterPointDigitCount should be non-negative.",
            )
        if minAfterPointDigitCount > maxAfterPointDigitCount:
            self.quitf(
                Outcome.FAIL,
                "stringToStrictDouble: minAfterPointDigitCount should be less or equal to maxAfterPointDigitCount.",
            )
        length = len(buffer)
        if length == 0 or length > 1000:
            self._expected("strict double", buffer)
        if buffer[0] != "-" and not ("0" <= buffer[0] <= "9"):
            self._expected("strict double", buffer)
        point_pos = -1
        for i in range(1, length - 1):
            ch = buffer[i]
            if ch == ".":
                if point_pos > -1:
                    self._expected("strict double", buffer)
                point_pos = i
            if ch != "." and not ("0" <= ch <= "9"):
                self._expected("strict double", buffer)
        if not ("0" <= buffer[length - 1] <= "9"):
            self._expected("strict double", buffer)
        after = 0 if point_pos == -1 else length - point_pos - 1
        if after < minAfterPointDigitCount or after > maxAfterPointDigitCount:
            self.quitf(
                Outcome.PE,
                "Expected strict double with number of digits after point in range "
                "[{},{}], but \"{}\" found".format(
                    minAfterPointDigitCount, maxAfterPointDigitCount, testlib_part(buffer)
                ),
            )
        first_digit = -1
        for i in range(length):
            if "0" <= buffer[i] <= "9":
                first_digit = i
                break
        if first_digit > 1 or first_digit == -1:
            self._expected("strict double", buffer)
        if (
            buffer[first_digit] == "0"
            and first_digit + 1 < length
            and "0" <= buffer[first_digit + 1] <= "9"
        ):
            self._expected("strict double", buffer)
        try:
            result = float(buffer)
        except ValueError:
            self._expected("double", buffer)
        if math.isnan(result) or math.isinf(result):
            self._expected("double", buffer)
        if buffer[0] == "-" and result >= 0:
            self.quitf(Outcome.PE, 'Redundant minus in "{}" found'.format(testlib_part(buffer)))
        return result

    def readInt(self, minv=None, maxv=None, variableName=""):
        """Read a signed 32-bit integer.

        With both bounds, a value outside ``[minv, maxv]`` is WA. A token
        that is an integer but does not fit in 32 bits is a presentation error.
        """
        if not self.strict and self.seekEof():
            self.quitf(Outcome.PE, "Unexpected end of file - int32 expected")
        token = self.readWord()
        value = self.stringToInt(token)
        if value < INT32_MIN or value > INT32_MAX:
            self._expected("int32", token)
        if _bounds_given(minv, maxv):
            self._check_bounds(value, minv, maxv, variableName, "Integer")
        return value

    def readInteger(self, minv=None, maxv=None, variableName=""):
        """Alias of ``readInt``."""
        return self.readInt(minv, maxv, variableName)

    def readLong(self, minv=None, maxv=None, variableName=""):
        """Read a signed 64-bit integer.

        With both bounds, a value outside ``[minv, maxv]`` is WA.
        """
        if not self.strict and self.seekEof():
            self.quitf(Outcome.PE, "Unexpected end of file - int64 expected")
        value = self.stringToInt(self.readWord())
        if _bounds_given(minv, maxv):
            self._check_bounds(value, minv, maxv, variableName, "Integer")
        return value

    def readUnsignedLong(self, minv=None, maxv=None, variableName=""):
        """Read an unsigned 64-bit integer, optionally within ``[minv, maxv]``."""
        if not self.strict and self.seekEof():
            self.quitf(Outcome.PE, "Unexpected end of file - int64 expected")
        value = self.stringToUnsignedLong(self.readWord())
        if _bounds_given(minv, maxv):
            self._check_bounds(value, minv, maxv, variableName, "Unsigned integer")
        return value

    def readInts(self, size, minv=None, maxv=None, variablesName="", indexBase=1):
        """Read ``size`` 32-bit integers.

        In strict mode the numbers are separated by single spaces. ``size``
        must be from 0 to 100000000. Indexes in range messages start at
        ``indexBase``.
        """
        def read_one():
            return self.readInt(minv, maxv, variablesName)
        return self._read_many("readInts", size, indexBase, read_one, True)

    def readIntegers(self, size, minv=None, maxv=None, variablesName="", indexBase=1):
        """Alias of ``readInts``."""
        return self.readInts(size, minv, maxv, variablesName, indexBase)

    def readLongs(self, size, minv=None, maxv=None, variablesName="", indexBase=1):
        """Read ``size`` 64-bit integers. See ``readInts``."""
        def read_one():
            return self.readLong(minv, maxv, variablesName)
        return self._read_many("readLongs", size, indexBase, read_one, True)

    def readUnsignedLongs(self, size, minv=None, maxv=None, variablesName="", indexBase=1):
        """Read ``size`` unsigned 64-bit integers. See ``readLongs``."""
        return self._read_many(
            "readUnsignedLongs", size, indexBase,
            lambda: self.readUnsignedLong(minv, maxv, variablesName), True,
        )

    def readFloat(self):
        """Read a floating-point token. See ``stringToFloat``."""
        return self.readDouble()

    def readDouble(self, minv=None, maxv=None, variableName=""):
        """Read a floating-point token.

        With both bounds, a value outside ``[minv, maxv]`` is WA.
        """
        if not self.strict and self.seekEof():
            self.quitf(Outcome.PE, "Unexpected end of file - double expected")
        value = self.stringToFloat(self.readWord())
        if _bounds_given(minv, maxv):
            self._check_bounds(value, minv, maxv, variableName, "Double")
        return value

    def readReal(self, minv=None, maxv=None, variableName=""):
        """Alias of ``readDouble``."""
        return self.readDouble(minv, maxv, variableName)

    def readDoubles(self, size, minv=None, maxv=None, variablesName="", indexBase=1):
        """Read ``size`` doubles. See ``readInts``."""
        def read_one():
            return self.readDouble(minv, maxv, variablesName)
        return self._read_many("readDoubles", size, indexBase, read_one, True)

    def readReals(self, size, minv=None, maxv=None, variablesName="", indexBase=1):
        """Alias of ``readDoubles``."""
        return self.readDoubles(size, minv, maxv, variablesName, indexBase)

    def readStrictDouble(
        self, minv, maxv, minAfterPointDigitCount, maxAfterPointDigitCount, variableName=""
    ):
        """Read a double with a fixed number of digits after the point.

        No exponent and no leading zeros. A value outside ``[minv, maxv]``
        is WA. The digit-count arguments are inclusive.
        """
        if not self.strict and self.seekEof():
            self.quitf(Outcome.PE, "Unexpected end of file - strict double expected")
        token = self.readWord()
        value = self.stringToStrictDouble(
            token, minAfterPointDigitCount, maxAfterPointDigitCount
        )
        self._check_bounds(value, minv, maxv, variableName, "Strict double")
        return value

    def readStrictDoubles(
        self,
        size,
        minv,
        maxv,
        minAfterPointDigitCount,
        maxAfterPointDigitCount,
        variablesName="",
        indexBase=1,
    ):
        """Read ``size`` strict doubles. See ``readInts`` and ``readStrictDouble``."""
        def read_one():
            return self.readStrictDouble(
                minv, maxv, minAfterPointDigitCount, maxAfterPointDigitCount, variablesName
            )
        return self._read_many("readStrictDoubles", size, indexBase, read_one, True)

    def readStrictReal(
        self, minv, maxv, minAfterPointDigitCount, maxAfterPointDigitCount, variableName=""
    ):
        """Alias of ``readStrictDouble``."""
        return self.readStrictDouble(
            minv, maxv, minAfterPointDigitCount, maxAfterPointDigitCount, variableName
        )

    def readStrictReals(
        self, size, minv, maxv, minAfterPointDigitCount,
        maxAfterPointDigitCount, variablesName="", indexBase=1,
    ):
        """Alias of ``readStrictDoubles``."""
        return self._read_many(
            "readStrictReals", size, indexBase,
            lambda: self.readStrictReal(
                minv, maxv, minAfterPointDigitCount, maxAfterPointDigitCount,
                variablesName,
            ), True,
        )

    def eof(self):
        """True at end of file, or when the stream was never opened."""
        if self.reader is None:
            return True
        return self.reader.eof()

    def eoln(self):
        """Return True if the next character starts a line break, and consume it.

        In checker mode a CR LF pair is one line break, a lone LF is a line
        break, a lone CR is put back, and EOF counts as a line break. In
        strict mode the break is CR LF on Windows and LF otherwise, and EOF
        is not a line break.
        """
        reader = self.reader
        if not self.strict and reader is None:
            return True
        if reader is None:
            self.quitf(Outcome.FAIL, "File is not opened: \"{}\"".format(self.name))
        c = reader.nextChar()
        if not self.strict:
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
        return_cr = False
        if os.name == "nt":
            if c != CR:
                reader.unreadChar(c)
                return False
            return_cr = True
            c = reader.nextChar()
        if c != LF:
            reader.unreadChar(c)
            if return_cr:
                reader.unreadChar(CR)
            return False
        return True

    def readEoln(self):
        """Require a line break. A missing break is a presentation error."""
        if self.reader is not None:
            self.lastLine = self.reader.line
        if not self.eoln():
            self.quitf(Outcome.PE, "Expected EOLN")

    def readEof(self):
        """Require end of file.

        On ``inf`` this records that a validator finished its input.
        """
        if self.reader is not None:
            self.lastLine = self.reader.line
        if not self.eof():
            self.quitf(Outcome.PE, "Expected EOF")
        if self is inf:
            finalizer.read_eof_count += 1

    def quitf(self, result, msg):
        """Finish the checker with ``result`` and ``msg``. Does not return.

        A verdict other than FAIL raised while reading the input or the
        answer is rewritten to FAIL: those files are the jury's, so a
        malformed token there is a checker or test error, not a
        participant's presentation error. A validator read error also
        names the line.

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
            if testlib_mode == "validator" and self.mode == FileMode.INPUT and self.lastLine != -1:
                where = "{}, line {}".format(self.name, self.lastLine)
            else:
                where = self.name
            self.quitf(Outcome.FAIL, "{} ({})".format(msg, where))

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
                            '<result outcome = "{}" points = "{}">'.format(
                                outcomes[result], _format_points(_quitp_points)
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


def ensure(cond, what):
    """Fail when ``cond`` is false.

    The report is ``Condition failed: "<what>"``. ``what`` is the text
    of the condition. This function does not return in that case.
    """
    if not cond:
        quitf(Outcome.FAIL, 'Condition failed: "{}"'.format(what))


def ensuref(cond, msg):
    """Fail with ``msg`` when ``cond`` is false. Does not return in that case."""
    if not cond:
        quitf(Outcome.FAIL, msg)


def quitp(points, msg):
    """Finish with a partial score. Does not return.

    A float is formatted like C++ ``%.10f`` with trailing zeros removed.
    An int is printed in decimal. The value must be finite, must not be
    negative, and must not exceed 1e6. This is the only supported way to
    report ``Outcome.POINTS``.
    """
    global _quitp_points
    if isinstance(points, bool) or not isinstance(points, (int, float)):
        quitf(Outcome.FAIL, "Parameter 'points' must be a real number")
    prepared = _prepare_points(points)
    _quitp_points = prepared
    if isinstance(points, int):
        shown = str(points)
    else:
        shown = _format_points(prepared)
    if msg:
        quitf(Outcome.POINTS, shown + " " + msg)
    else:
        quitf(Outcome.POINTS, shown)


inf = InStream()
ouf = InStream()
ans = InStream()


class TestlibFinalizeGuard:
    """Exit with FAIL when a registered checker returns without ``quitf``."""

    def __init__(self):
        self.quit_count = 0
        self.read_eof_count = 0
        self.alive = True

    def finalize(self):
        cur_alive = self.alive
        self.alive = False
        if not cur_alive:
            return
        if testlib_mode == "validator":
            if self.quit_count == 0 and self.read_eof_count == 0:
                quitf(Outcome.FAIL, "Validator must end with readEof call.")
            return
        if self.quit_count != 0:
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


_VALIDATOR_ARGUMENTS = (
    "Validator must be run with the following arguments:"
    " [--testset testset]"
    " [--group group]"
    " [--testOverviewLogFileName fileName]"
    " [--testMarkupFileName fileName]"
    " [--testCase testCase]"
    " [--testCaseFileName fileName]"
)

_MAX_TEST_CASE = 1073741823


class Validator:
    """Testset and group selected on the validator command line.

    ``testset`` is ``"tests"`` when ``registerValidation`` receives
    ``argv`` and ``--testset`` is absent. Both accessors fail when
    validation was started without ``argv``.
    """

    def __init__(self):
        self._initialized = False
        self._testset = "tests"
        self._group = ""

    def reset(self):
        """Forget the command line and the initialization flag."""
        self._initialized = False
        self._testset = "tests"
        self._group = ""

    def initialize(self):
        """Allow ``testset`` and ``group`` to be read."""
        self._initialized = True

    def testset(self):
        """Return the active testset name."""
        if not self._initialized:
            quitf(
                Outcome.FAIL,
                "Validator should be initialized with registerValidation(argc, argv) "
                "instead of registerValidation() to support validator.testset()",
            )
        return self._testset

    def group(self):
        """Return the active group name. It is empty when ``--group`` is absent."""
        if not self._initialized:
            quitf(
                Outcome.FAIL,
                "Validator should be initialized with registerValidation(argc, argv) "
                "instead of registerValidation() to support validator.group()",
            )
        return self._group


validator = Validator()


def _register_validation_flags(argv):
    index = 1
    while index < len(argv):
        flag = argv[index]
        if flag == "--testset":
            if index + 1 < len(argv) and argv[index + 1] != "":
                validator._testset = argv[index + 1]
                index += 2
                continue
            quitf(Outcome.FAIL, _VALIDATOR_ARGUMENTS)
        if flag == "--group":
            if index + 1 < len(argv):
                validator._group = argv[index + 1]
                index += 2
                continue
            quitf(Outcome.FAIL, _VALIDATOR_ARGUMENTS)
        if flag in (
            "--testOverviewLogFileName",
            "--testMarkupFileName",
            "--testCaseFileName",
        ):
            if index + 1 < len(argv):
                index += 2
                continue
            quitf(Outcome.FAIL, _VALIDATOR_ARGUMENTS)
        if flag == "--testCase":
            if index + 1 >= len(argv):
                quitf(Outcome.FAIL, _VALIDATOR_ARGUMENTS)
            test_case = inf.stringToInt(argv[index + 1])
            if test_case < 1 or test_case >= _MAX_TEST_CASE:
                quitf(
                    Outcome.FAIL,
                    "Argument testCase should be between 1 and {}, but {} found".format(
                        _MAX_TEST_CASE, test_case
                    ),
                )
            index += 2
            continue
        index += 1


def registerValidation(argv=None):
    """Read the input from stdin in strict mode.

    A validator must finish with ``inf.readEof()`` and does not call
    ``quitf`` when the input is accepted. Pass ``argv`` to accept the
    optional ``--testset`` and ``--group`` flags and to enable
    ``validator.testset`` and ``validator.group``.
    """
    global testlib_mode, _quitp_points, _last_exception
    testlib_mode = "validator"
    _quitp_points = None
    _last_exception = None
    validator.reset()
    _install_hooks()
    inf.init_stdin()
    inf.strict = True
    if argv is not None:
        _register_validation_flags(argv)
        validator.initialize()


def registerTestlibCmd():
    """Open the checker files from ``sys.argv`` and arm the exit guard.

    See the module docstring for the command line. ``--help`` exits with
    FAIL and the argument contract.
    """
    global result_name, appes_mode, _quitp_points, _last_exception, testlib_mode
    testlib_mode = "checker"
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
