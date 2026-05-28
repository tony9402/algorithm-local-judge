"""컴파일러와 실행기 테스트가 정상 제출 경로를 재현할 수 있도록 순열 출력을 제공하는 Python 픽스처입니다."""

import sys


def permutation(n, m, selected, used):
    """선택 여부 배열을 이용해 길이가 정해진 순열을 재귀적으로 출력합니다.

    Args:
        n (int): 순열을 생성할 숫자 범위의 끝값입니다.
        m (int): 출력할 순열 길이입니다.
        selected (list[int]): 순열 생성 중 현재까지 선택한 숫자 목록입니다.
        used (list[bool]): 순열 생성에서 이미 선택된 숫자를 표시하는 배열입니다.
    """
    if len(selected) == m:
        print(*selected)
        return
    for value in range(1, n + 1):
        if used[value]:
            continue
        used[value] = True
        selected.append(value)
        permutation(n, m, selected, used)
        selected.pop()
        used[value] = False


def main():
    """표준 입력에서 순열 크기를 읽고 정답 제출 픽스처가 기대하는 순열 출력을 생성합니다."""
    data = sys.stdin.read().split()
    n, m = map(int, data[:2])
    permutation(n, m, [], [False] * (n + 1))


if __name__ == "__main__":
    main()
