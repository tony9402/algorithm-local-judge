import sys


def permutation(n, m, selected, used):
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
    data = sys.stdin.read().split()
    n, m = map(int, data[:2])
    permutation(n, m, [], [False] * (n + 1))


if __name__ == "__main__":
    main()
