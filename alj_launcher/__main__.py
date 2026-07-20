"""실행 파일 이름에 따라 standalone 제품 진입점을 선택합니다."""

from __future__ import annotations

import sys
from pathlib import Path

from judge.cli import main as judge_main
from problem_studio.cli import main as problem_studio_main


def main() -> int:
    """`judge` 또는 `problem-studio` 실행 파일에 맞는 CLI를 실행합니다."""
    if Path(sys.argv[0]).stem.lower() == "problem-studio":
        return problem_studio_main()
    return judge_main()


if __name__ == "__main__":
    raise SystemExit(main())
