# Testlib (C++ and Python versions)

## Intro

C++ version of testlib is MikeMirzayanov's one (
[https://github.com/MikeMirzayanov/testlib](https://github.com/MikeMirzayanov/testlib)
).

The project also contains Python implementation of the testlib. This
version is used on some competitions on Yandex.Contest (
[https://contest.yandex.com](https://contest.yandex.com) ).

The Python version is a single-file library for checkers and validators,
tested for Yandex.Contest. It supports verdicts and partial scores, patterns,
strict validator input, signed and unsigned 64-bit integers, arrays of tokens
and lines, and strict decimal reads. It does not support generators,
interactors, or the complete C++ testlib API. See the `testlib.py` module
docstring for the checker command line and report format.

Pascal version of testlib is not included, but can be found at
[http://acm.math.spbu.ru/soft/testlib](http://acm.math.spbu.ru/soft/testlib)
or [clone](https://github.com/stden/testlib) on github.

This project contains a C++ implementation of testlib. It is already being used in many programming contests in Russia, such as the Russian National Olympiad in Informatics and different stages of ICPC. Join!

The library's C++ code is tested for compatibility with standard C++11 and higher on different versions of `g++`, `clang++`, and Microsoft Visual C++.

This code has been used many times in Codeforces contests.

## Samples

### Checker (C++ and Python)

This sample checker expects the same integer in the output and the answer. It ignores all white-spaces. See more examples in the package.

```c++
#include "testlib.h"

int main(int argc, char * argv[]) {
    setName("compares two signed integers");
    registerTestlibCmd(argc, argv);
    int ja = ans.readInt();
    int pa = ouf.readInt();
    if (ja != pa)
        quitf(_wa, "expected %d, found %d", ja, pa);
    quitf(_ok, "answer is %d", ja);
}
```

```python
#!/usr/bin/python3
from testlib import *


if __name__ == '__main__':
    """
    compares two signed integers
    """
    registerTestlibCmd()
    ja = ans.readInt()
    pa = ouf.readInt()
    if ja != pa:
        quitf(Outcome.WA, "expected {}, found {}".format(ja, pa))
    quitf(Outcome.OK, "answer is {}".format(ja))
```

### Interactor (C++ only)

This sample interactor reads pairs of numbers from the input file, sends them to another program, reads
the result, and writes it to an output file (to be verified later). Another option could be to terminate
the interactor with `quitf(_wa, <comment>)`.

```c++
#include "testlib.h"
#include <iostream>

using namespace std;

int main(int argc, char* argv[]) {
    setName("Interactor A+B");
    registerInteraction(argc, argv);

    // reads number of queries from test (input) file
    int n = inf.readInt();
    for (int i = 0; i < n; i++) {
        // reads query from test (input) file
        int a = inf.readInt();
        int b = inf.readInt();

        // writes query to the solution, endl makes flush
        cout << a << " " << b << endl;

        // writes output file to be verified by checker later
        tout << ouf.readInt() << endl;
    }

    // just message
    quitf(_ok, "%d queries processed", n);
}
```

### Validator (C++ and Python)

This code reads input from standard input and checks that it contains only one integer between 1 and 100, inclusive. It also validates that the file ends with EOLN and EOF. On Windows, it expects #13#10 as EOLN, and it expects #10 as EOLN on other platforms. It does not ignore white-spaces, so it works very strictly. Invalid input produces a non-zero exit code and an error message. See more examples in the package.

```c++
#include "testlib.h"

int main(int argc, char* argv[]) {
    registerValidation(argc, argv);
    inf.readInt(1, 100, "n");
    inf.readEoln();
    inf.readEof();
}
```

```python
#!/usr/bin/python3
import sys
from testlib import *


if __name__ == "__main__":
    registerValidation(sys.argv)
    inf.readInt(1, 100, "n")
    inf.readEoln()
    inf.readEof()
```

The Python validator reads standard input strictly and must finish with
`inf.readEof()`. See `validators/` for more examples, including arrays,
patterns, and command-line `--testset`/`--group` flags. Put `testlib.py`
beside the checker or validator script, or include the repository directory
on `PYTHONPATH`.

Python regression tests run on Linux and Windows in CI. Run them locally with
`python -B -m unittest discover -s tests -p "test_*.py" -v`.

### Questionnaire checker (Python)

`checkers/questions_checker.py` reads one answer per non-empty line:
`Q1 value`, `Q2 value1 value2`, and so on. Keys are case-insensitive and
must be `Q1`, `Q2`, etc.; duplicate keys are a presentation error. The
default comparison keeps token order, ignores text case, and compares finite
numbers with an absolute tolerance of `0.0015`.

Edit `QUESTION_RULES` near the top of the checker to configure individual
questions, for example:

```python
QUESTION_RULES = {
    "Q1": {"kind": "number", "abs_tol": 0.01, "inclusive": False, "points": 2},
    "Q2": {"kind": "unordered", "points": 3, "required": False},
    "Q3": {"kind": "text", "case_sensitive": True, "points": 1},
}
```

`kind` can be `auto`, `number` (one finite number), `text`, or
`unordered` (a multiset of text tokens). Adding `points` enables partial
scoring: missing or wrong optional questions earn zero, including when the
total score is zero. Without scoring, questions are required by default.
`required` can override either default. The `POINTS` mapping also
works; per-question `points` takes precedence. Feedback names incorrect
questions without revealing jury answers. `inclusive=False` uses a strict
numeric tolerance boundary.

### CSV checker (Python)

`checkers/csv_checker.py` compares a submitted CSV file (`ouf`) against the
jury CSV (`ans`). It reads UTF-8 (including a BOM), quoted commas, escaped
quotes, and quoted newlines with Python's `csv` parser. Every row must have
the declared number of columns; empty or repeated column names are rejected.
By default, header and row order must match, and all columns are compared.

Configure the constants near the top of a copy of the checker:

```python
KEY_COLUMN = "record_id"     # None compares rows by position
ALLOW_COLUMN_REORDER = True  # False requires the jury column order
COLUMN_RULES = {
    "measurement": {"kind": "number", "abs_tol": 0.01, "inclusive": False},
    "category": {"kind": "text"},
    "metadata": {"kind": "ignore"},
}
POINTS = 10                 # None returns OK/WA without a partial score
SCORE_MODE = "all_or_nothing"  # or "fraction_correct"
```

Kinds are `auto` (the default: compare finite decimal pairs numerically,
otherwise compare text), `number`, `text`, and `ignore`. Numeric rules also
accept `rel_tol`; text rules accept `case_sensitive` (true by default).
`inclusive` is true by default. With `KEY_COLUMN`, keys must be nonempty and
unique in both files; the checker matches rows by key. In `fraction_correct`
mode, the score is `POINTS * correct_rows / max(jury_rows, submitted_rows)`,
so extra or missing rows reduce it. Feedback reports counts without exposing
jury cell values. To compare only selected columns, mark the other columns
`ignore`; the full header is still validated.

### Generator (C++ only)

This generator outputs a random token to the standard output, containing Latin letters or digits. The length of the token will be between 1 and 1000, inclusive. It will use a uniformly distributed random generator. To generate different values, call it with different command-line parameters. It is typical behavior for a testlib generator to set up randseed by command line. See more examples in the package.

```c++
#include "testlib.h"

int main(int argc, char* argv[]) {
    registerGen(argc, argv, 1);
    println(rnd.next(1, 10)); /* Random number in the range [1,10]. */
    println(rnd.next("[a-zA-Z0-9]{1,1000}")); /* Random word of length [1,1000]. */
}
```

This generator outputs a random permutation; the size is equal to the first command-line argument.

```c++
#include "testlib.h"

int main(int argc, char* argv[]) {
    registerGen(argc, argv, 1);
    
    int n = opt<int>(1);
    println(n);
    println(rnd.perm(n, 1));
}
```
