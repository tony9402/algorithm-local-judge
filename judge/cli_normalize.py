from __future__ import annotations

from collections.abc import Sequence

from judge.cli_dispatch import COMMAND_HANDLERS
from judge.core.errors import JudgeError

RUN_GLOBAL_OPTIONS_WITH_VALUES = {"--problem", "--profile"}


def run_global_option_name(token: str) -> str | None:
    """Return the run-global option name represented by a token."""
    if token in RUN_GLOBAL_OPTIONS_WITH_VALUES:
        return token
    for option in RUN_GLOBAL_OPTIONS_WITH_VALUES:
        if token.startswith(option + "="):
            return option
    return None


def run_global_command_error(option: str, command: str) -> JudgeError:
    """Build a clear error for run-only options before other commands."""
    hint = {
        "generate": "judge generate <problem> --profile <profile>",
        "cache": "judge cache clear --problem <problem> --dry-run",
    }.get(command, f"judge {command} ...")
    return JudgeError(f"global {option} can only be used with run; use `{hint}`")


def normalize_argv(argv: Sequence[str]) -> list[str]:
    """Insert an explicit `run` command for supported shorthand invocations."""
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
