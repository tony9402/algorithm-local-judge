from __future__ import annotations

import argparse
from pathlib import Path


def cleanup_inplace(file_path: str | Path, only_last: bool) -> None:
    """Trim trailing whitespace in a generated data file."""
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
    """Parse cleanup CLI arguments."""
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
