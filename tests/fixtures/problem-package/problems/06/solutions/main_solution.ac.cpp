#include <iostream>
#include <vector>

int n = 0;
int m = 0;
std::vector<int> selected;
std::vector<bool> used;

void permutation() {
    if (static_cast<int>(selected.size()) == m) {
        for (int index = 0; index < m; ++index) {
            if (index > 0) {
                std::cout << ' ';
            }
            std::cout << selected[index];
        }
        std::cout << '\n';
        return;
    }
    for (int value = 1; value <= n; ++value) {
        if (used[value]) {
            continue;
        }
        used[value] = true;
        selected.push_back(value);
        permutation();
        selected.pop_back();
        used[value] = false;
    }
}

int main() {
    std::cin >> n >> m;
    used.assign(n + 1, false);
    permutation();
    return 0;
}
