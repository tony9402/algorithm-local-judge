#include <fstream>
#include <iterator>
#include <string>
#include <vector>

std::vector<std::string> tokens(const char* path) {
    std::ifstream input(path);
    return {
        std::istream_iterator<std::string>(input),
        std::istream_iterator<std::string>(),
    };
}

int main(int argc, char** argv) {
    if (argc < 4) {
        return 1;
    }
    return tokens(argv[2]) == tokens(argv[3]) ? 0 : 1;
}
