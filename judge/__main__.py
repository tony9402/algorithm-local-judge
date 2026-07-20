from judge.cli import main as judge_main


def main() -> int:
    """Judge 명령행 진입점을 실행합니다."""
    return judge_main()


if __name__ == "__main__":
    raise SystemExit(main())
