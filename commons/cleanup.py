"""생성된 데이터 파일의 줄 끝 공백을 정리하는 명령줄 유틸리티입니다."""
from __future__ import annotations

import argparse
from pathlib import Path


def cleanup_inplace(file_path: str | Path, only_last: bool) -> None:
    """지정한 데이터 파일을 제자리에서 열어 줄 끝 공백을 제거합니다. 전체 줄을 정리하거나 마지막 줄만 정리하는 두 모드를 지원합니다.

    Args:
        file_path (str | Path): 공백 정리를 적용할 데이터 파일 경로입니다.
        only_last (bool): 참이면 마지막 줄만 정리하고, 거짓이면 모든 줄의 오른쪽 공백을 정리합니다.
    """
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    if only_last:
        lines[-1] = lines[-1].rstrip()
    else:
        lines = [line.rstrip() for line in lines]

    with path.open("w", encoding="utf-8") as f:
        f.writelines(lines)


def parse_args() -> argparse.Namespace:
    """공백 정리 명령에서 사용할 대상 파일 경로와 마지막 줄 정리 옵션을 파싱합니다.

    Returns:
        argparse.Namespace: `file_path`와 `only_last` 값을 담은 명령줄 인자 네임스페이스입니다.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", dest="file_path", help="데이터 파일 경로", required=True)
    parser.add_argument(
        "--only-last", help="데이터 파일 맨 끝에만 정리하는 경우", action="store_false"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    cleanup_inplace(
        file_path=args.file_path,
        only_last=args.only_last,
    )
