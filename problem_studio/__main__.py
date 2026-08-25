"""``python -m problem_studio`` 호환 진입점을 제공합니다."""

from problem_studio.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
