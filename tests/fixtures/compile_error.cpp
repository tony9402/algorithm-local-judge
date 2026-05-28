// 컴파일 실패 경로가 컴파일 로그와 종료 상태를 남기는지 확인하는 C++ 픽스처입니다.
// 의도적으로 잘못된 식별자를 사용해 컴파일러 오류를 재현합니다.

#include <iostream>

int main() {
    std::cout << "missing semicolon\n"
    return 0;
}
