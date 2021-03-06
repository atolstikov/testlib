# Testlib (C++ and Python versions)

## Intro

C++ version of testlib is MikeMirzayanov's one (
[https://github.com/MikeMirzayanov/testlib](https://github.com/MikeMirzayanov/testlib)
).

The project also contains Python implementation of the testlib. This
version is used on some competitions on Yandex.Contest (
[https://contest.yandex.com](https://contest.yandex.com) ).

Pascal version of testlib is not include, but can be found at
[http://acm.math.spbu.ru/soft/testlib](http://acm.math.spbu.ru/soft/testlib)
or [clone](https://github.com/stden/testlib) on github.

## Samples

### Checker (C++ and Python)

This is sample checker which expects in the output and in the answer the same integer. It ignores all white-spaces. See more examples in the package.

```c++
#include "testlib.h"

int main(int argc, char * argv[])
{
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

This sample interactor reads pairs of numbers from input file, sends it to the other program, reads
result and writes it to output file (to be verified later). Another option could be terminating
interactor with `quitf(_wa, <comment>)`.

```c++
#include "testlib.h"
#include <iostream>

using namespace std;

int main(int argc, char* argv[])
{
    setName("Interactor A+B");
    registerInteraction(argc, argv);

    // reads number of queries from test (input) file
    int n = inf.readInt();
    for (int i = 0; i < n; i++)
    {
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

### Validator (C++ only)

This code reads input from the standard input and checks that it contains the only integer between 1 and 100, inclusive. Also validates that file ends with EOLN and EOF. On Windows it expects #13#10 as EOLN and it expects #10 as EOLN on other platforms. It doesn't ignore white-spaces, so it works very strict. It will return non-zero code in case of illegal input and writes message into the standard output. See more examples in the package.


```c++
#include "testlib.h"

int main(int argc, char* argv[])
{
    registerValidation(argc, argv);
    inf.readInt(1, 100);
    inf.readEoln();
    inf.readEof();
}
```

### Generator (C++ only)

This generator outputs into the standard output random token, containing Latin letters or digits. The length of the token will be between 1 and 1000, inclusive. It will use uniformly distributed random. To generate different values, call it with different command line parameters. It is typical behaviour of testlib generator to setup randseed by command line. See more examples in the package.

```c++
#include "testlib.h"
#include <iostream>

using namespace std;

int main(int argc, char* argv[])
{
    registerGen(argc, argv, 1);
    cout << rnd.next(1, 10) << endl; /* Random number in the range [1,10]. */
    cout << rnd.next("[a-zA-Z0-9]{1,1000}") << endl;  /* Random word of length [1,1000]. */
}
```

This generator outputs random permutation, the size equals to the first command line argument.

```c++
#include "testlib.h"

using namespace std;

int main(int argc, char* argv[]) {
    registerGen(argc, argv, 1);
    
    int n = atoi(argv[1]);
    println(n);
    println(rnd.perm(n, 1));
}
```
