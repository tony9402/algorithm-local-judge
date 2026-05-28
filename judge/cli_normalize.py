"""cli_normalize 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from collections.abc import Sequence

from judge.cli_dispatch import COMMAND_HANDLERS
from judge.core.errors import JudgeError

RUN_GLOBAL_OPTIONS_WITH_VALUES = {"--problem", "--profile"}


def run_global_option_name(token: str) -> str | None:
    """run_global_option_name 함수를 실행하고 결과를 반환합니다.
    
    Args:
        token (str): `token` 값입니다.
    
    Returns:
        str | None: 처리 결과를 반환합니다.
    """
    if token in RUN_GLOBAL_OPTIONS_WITH_VALUES:
        return token
    for option in RUN_GLOBAL_OPTIONS_WITH_VALUES:
        if token.startswith(option + "="):
            return option
    return None


def run_global_command_error(option: str, command: str) -> JudgeError:
    """run_global_command_error 함수를 실행하고 결과를 반환합니다.
    
    Args:
        option (str): 옵션입니다.
        command (str): `command` 값입니다.
    
    Returns:
        JudgeError: 처리 결과를 반환합니다.
    """
    hint = {
        "generate": "judge generate <problem> --profile <profile>",
        "cache": "judge cache clear --problem <problem> --dry-run",
    }.get(command, f"judge {command} ...")
    return JudgeError(f"global {option} can only be used with run; use `{hint}`")


def normalize_argv(argv: Sequence[str]) -> list[str]:
    """normalize_argv 함수를 실행하고 결과를 반환합니다.
    
    Args:
        argv (Sequence[str]): `argv` 값입니다.
    
    Returns:
        list[str]: 처리 결과를 반환합니다.
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
