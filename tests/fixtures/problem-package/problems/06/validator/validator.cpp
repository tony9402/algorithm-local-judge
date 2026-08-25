#include <iostream>

int main() {
    int n = 0;
    int m = 0;
    if (!(std::cin >> n >> m)) {
        return 1;
    }
    if (n < 1 || n > 8 || m < 1 || m > n) {
        return 1;
    }
    std::cin >> std::ws;
    return std::cin.eof() ? 0 : 1;
}
