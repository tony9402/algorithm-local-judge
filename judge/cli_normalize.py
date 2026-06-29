"""CLI normalize 기능을 담당하는 모듈입니다.
"""
from __future__ import annotations

from collections.abc import Sequence

from judge.cli_dispatch import COMMAND_HANDLERS
from judge.core.errors import JudgeError

RUN_GLOBAL_OPTIONS_WITH_VALUES = {"--problem", "--profile", "--language"}


def run_global_option_name(token: str) -> str | None:
    """global option 이름 실행에 필요한 입력을 준비하고 외부 프로세스나 서비스 호출을 수행합니다.

        Args:
            token (str): global option 이름을 계산하거나 검증할 때 필요한 token 입력입니다.
    """
    if token in RUN_GLOBAL_OPTIONS_WITH_VALUES:
        return token
    for option in RUN_GLOBAL_OPTIONS_WITH_VALUES:
        if token.startswith(option + "="):
            return option
    return None


def run_global_command_error(option: str, command: str) -> JudgeError:
    """global 명령 오류 실행에 필요한 입력을 준비하고 외부 프로세스나 서비스 호출을 수행합니다.

        Args:
            option (str): global 명령 오류을 계산하거나 검증할 때 필요한 option 입력입니다.
            command (str): global 명령 오류을 계산하거나 검증할 때 필요한 명령 입력입니다.
    """
    hint = {
        "generate": "judge generate <problem> --profile <profile>",
        "cache": "judge cache clear --problem <problem> --dry-run",
    }.get(command, f"judge {command} ...")
    return JudgeError(f"global {option} can only be used with run; use `{hint}`")


def normalize_argv(argv: Sequence[str]) -> list[str]:
    """argv 입력을 비교와 저장에 쓰기 쉬운 표준 형식으로 정규화합니다.

    Args:
        argv (Sequence[str]): 프로그램 이름을 제외한 CLI 인자 목록입니다. None이면 현재 프로세스의 인자를 읽습니다.

    Returns:
        list[str]: 호출자가 순회하거나 화면에 표시할 argv 항목 목록입니다.
    """
    argv = list(argv)
    if not argv:
        return argv
    if argv in (["-h"], ["--help"]):
        return argv

    seen_run_globals = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--":
            return argv[:index] + ["run"] + argv[index:]

        run_global_option = run_global_option_name(token)
        if run_global_option:
            seen_run_globals.append(run_global_option)
        if token in RUN_GLOBAL_OPTIONS_WITH_VALUES:
            index += 2
            continue
        if run_global_option:
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        if token in COMMAND_HANDLERS:
            if seen_run_globals and token != "run":
                raise run_global_command_error(seen_run_globals[0], token)
            return argv
        return argv[:index] + ["run"] + argv[index:]
    return argv
