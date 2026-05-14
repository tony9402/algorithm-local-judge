from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from judge.commands import cache as cache_command
from judge.commands import cases as cases_command
from judge.commands import compile as compile_command
from judge.commands import diff as diff_command
from judge.commands import generate as generate_command
from judge.commands import list as list_command
from judge.commands import pack as pack_command
from judge.commands import run as run_command
from judge.commands import show as show_command
from judge.commands import web as web_command
from judge.core.errors import JudgeError
from judge.core.paths import current_platform_id

COMMAND_HANDLERS = {
    "compile": compile_command.handle,
    "cases": cases_command.handle,
    "list": list_command.handle,
    "generate": generate_command.handle,
    "run": run_command.handle,
    "show": show_command.handle,
    "diff": diff_command.handle,
    "cache": cache_command.handle,
    "pack": pack_command.handle,
    "web": web_command.handle,
}
RUN_GLOBAL_OPTIONS_WITH_VALUES = {"--problem", "--profile"}


def add_parser(subparsers: argparse._SubParsersAction, name: str) -> argparse.ArgumentParser:
    """Add a subparser with option abbreviation disabled."""
    return subparsers.add_parser(name, allow_abbrev=False)


def add_common_run_args(parser: argparse.ArgumentParser) -> None:
    """Register options shared by explicit run commands."""
    parser.add_argument("--problem", dest="run_problem")
    parser.add_argument("--profile", dest="run_profile")


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser and all subcommands."""
    parser = argparse.ArgumentParser(prog="judge", allow_abbrev=False)
    parser.add_argument("--problem")
    parser.add_argument("--profile")
    subparsers = parser.add_subparsers(dest="command")

    compile_parser = add_parser(subparsers, "compile")
    compile_parser.add_argument("problem")

    cases_parser = add_parser(subparsers, "cases")
    cases_sub = cases_parser.add_subparsers(dest="cases_command", required=True)
    cases_compile = cases_sub.add_parser("compile", allow_abbrev=False)
    cases_compile.add_argument("problem", nargs="?")
    cases_compile.add_argument("--file")
    cases_compile.add_argument("--profile")
    cases_compile.add_argument("--expanded", action="store_true")
    cases_compile.add_argument("--max-preview", type=int)
    cases_compile.add_argument("--json", action="store_true")

    list_parser = add_parser(subparsers, "list")
    list_parser.add_argument("--validate", action="store_true")

    generate_parser = add_parser(subparsers, "generate")
    generate_parser.add_argument("problem")
    generate_parser.add_argument("--profile")
    generate_parser.add_argument("--force", action="store_true")

    run_parser = add_parser(subparsers, "run")
    add_common_run_args(run_parser)
    run_parser.add_argument("code_file")

    show_parser = add_parser(subparsers, "show")
    show_parser.add_argument("run_id")
    show_parser.add_argument("case_id")
    group = show_parser.add_mutually_exclusive_group()
    group.add_argument("--input", action="store_const", dest="part", const="input")
    group.add_argument("--expected", action="store_const", dest="part", const="expected")
    group.add_argument("--actual", action="store_const", dest="part", const="actual")

    diff_parser = add_parser(subparsers, "diff")
    diff_parser.add_argument("run_id")
    diff_parser.add_argument("case_id")

    cache_parser = add_parser(subparsers, "cache")
    cache_sub = cache_parser.add_subparsers(dest="cache_command", required=True)
    cache_sub.add_parser("status", allow_abbrev=False)
    clear_parser = cache_sub.add_parser("clear", allow_abbrev=False)
    clear_parser.add_argument("--problem")
    clear_parser.add_argument("--profile")
    clear_parser.add_argument("--runs", action="store_true")
    clear_parser.add_argument("--all", action="store_true")
    clear_parser.add_argument("--dry-run", action="store_true")
    clear_parser.add_argument("--yes", action="store_true")

    pack_parser = add_parser(subparsers, "pack")
    pack_sub = pack_parser.add_subparsers(dest="pack_command", required=True)
    pack_build = pack_sub.add_parser("build", allow_abbrev=False)
    pack_build.add_argument("problem_path")
    pack_build.add_argument("--pack-id", required=True)
    pack_build.add_argument("--platform", default=current_platform_id())
    pack_build.add_argument("--out", default="dist/packs")
    pack_verify = pack_sub.add_parser("verify", allow_abbrev=False)
    pack_verify.add_argument("archive")
    pack_install = pack_sub.add_parser("install", allow_abbrev=False)
    pack_install.add_argument("archive")
    pack_sub.add_parser("list", allow_abbrev=False)
    pack_remove = pack_sub.add_parser("remove", allow_abbrev=False)
    pack_remove.add_argument("pack_id")

    web_parser = add_parser(subparsers, "web")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8765)
    web_parser.add_argument("--open", action="store_true")
    web_parser.add_argument("--debug", action="store_true")

    return parser


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


def dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Dispatch parsed arguments to the selected command handler."""
    if args.command is None:
        parser.print_help()
        return 1

    try:
        handler = COMMAND_HANDLERS[args.command]
    except KeyError as exc:
        raise JudgeError(f"unknown command: {args.command}") from exc
    return handler(args)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint returning a process exit code."""
    parser = build_parser()
    explicit_argv = sys.argv[1:] if argv is None else argv
    try:
        args = parser.parse_args(normalize_argv(explicit_argv))
        result = dispatch(args, parser)
        return 0 if result is None else result
    except JudgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
