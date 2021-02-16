/*
 * Outputs random token from pattern.
 *
 * Token contains result of rnd.next(argv[1]).
 *
 * To generate different values, call "pgen.exe" with different parameters.
 * 
 * It is typical behaviour of testlib generator to setup randseed by command line.
 */

#include "testlib.h"
#include <iostream>

using namespace std;

int main(int argc, char* argv[])
{
    registerGen(argc, argv, 1);
    
    cout << rnd.next(argv[1]) << endl;

    return 0;
}
