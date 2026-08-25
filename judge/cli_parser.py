"""CLI parser 기능을 담당하는 모듈입니다."""

from __future__ import annotations

import argparse

from alj_core.studio_cli_options import add_web_arguments as add_studio_web_arguments
from judge import __version__
from judge.core.paths import current_platform_id


def add_parser(subparsers: argparse._SubParsersAction, name: str) -> argparse.ArgumentParser:
    return subparsers.add_parser(name, allow_abbrev=False)


def add_common_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--problem", dest="run_problem")
    parser.add_argument("--profile", dest="run_profile")
    parser.add_argument(
        "--language",
        dest="run_language",
        choices=["cpp", "python", "pypy", "java"],
    )


def build_parser() -> argparse.ArgumentParser:
    """parser에 필요한 경로, 메타데이터, 파일 목록을 조립합니다.

    Returns:
        argparse.ArgumentParser: 공통 옵션과 하위 명령이 등록된 argparse 파서입니다.
    """
    parser = argparse.ArgumentParser(prog="judge", allow_abbrev=False)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--problem")
    parser.add_argument("--profile")
    parser.add_argument("--language", choices=["cpp", "python", "pypy", "java"])
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

    doctor_parser = add_parser(subparsers, "doctor")
    doctor_parser.add_argument("--verbose", action="store_true")
    doctor_parser.add_argument("--json", action="store_true")

    docker_parser = add_parser(subparsers, "docker")
    docker_sub = docker_parser.add_subparsers(dest="docker_command", required=True)
    docker_sub.add_parser("setup", allow_abbrev=False)
    docker_web = docker_sub.add_parser("web", allow_abbrev=False)
    docker_web.add_argument("--port", type=int, default=8765)

    setup_parser = add_parser(subparsers, "setup")
    setup_parser.add_argument(
        "--repository",
        default="tony9402/algorithm-package",
        help="trusted problem repository installed when no problems are present",
    )
    setup_parser.add_argument("--check-only", action="store_true")
    setup_parser.add_argument(
        "--toolchains",
        choices=["auto", "managed", "system", "none"],
        default="auto",
    )
    setup_parser.add_argument("--yes", action="store_true")
    setup_parser.add_argument("--no-install-problems", action="store_true")
    setup_parser.add_argument("--no-web", action="store_true")
    setup_parser.add_argument("--no-open", action="store_true")
    setup_parser.add_argument("--port", type=int, default=8765)
    setup_parser.add_argument("--verbose", action="store_true")

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
    pack_build.add_argument("--verify-profile", default="hidden")
    pack_verify = pack_sub.add_parser("verify", allow_abbrev=False)
    pack_verify.add_argument("archive")
    pack_sign = pack_sub.add_parser("sign", allow_abbrev=False)
    pack_sign.add_argument("archive")
    pack_sign.add_argument("--bundle")
    pack_sign.add_argument("--key")
    pack_verify_signature = pack_sub.add_parser("verify-signature", allow_abbrev=False)
    pack_verify_signature.add_argument("archive")
    pack_verify_signature.add_argument("--bundle")
    pack_verify_signature.add_argument("--repository")
    pack_install = pack_sub.add_parser("install", allow_abbrev=False)
    pack_install.add_argument("archive")
    pack_sub.add_parser("list", allow_abbrev=False)
    pack_remove = pack_sub.add_parser("remove", allow_abbrev=False)
    pack_remove.add_argument("pack_id")
    pack_remove_all = pack_sub.add_parser("remove-all", allow_abbrev=False)
    pack_remove_all.add_argument("--confirm", action="store_true", required=True)
    pack_trust = pack_sub.add_parser("trust", allow_abbrev=False)
    pack_trust_sub = pack_trust.add_subparsers(dest="trust_command", required=True)
    pack_trust_sub.add_parser("list", allow_abbrev=False)
    pack_trust_add = pack_trust_sub.add_parser("add", allow_abbrev=False)
    pack_trust_add.add_argument("repository")
    pack_trust_remove = pack_trust_sub.add_parser("remove", allow_abbrev=False)
    pack_trust_remove.add_argument("repository")

    problem_parser = add_parser(subparsers, "problem")
    problem_sub = problem_parser.add_subparsers(dest="problem_command", required=True)
    problem_install = problem_sub.add_parser("install", allow_abbrev=False)
    problem_install.add_argument("source", nargs="?")
    problem_install.add_argument("--asset")
    problem_install.add_argument("--ref")
    problem_install.add_argument("--checksum")
    problem_install.add_argument("--checksum-url")
    problem_install.add_argument("--signature-url")
    problem_install.add_argument("--require-pack", action="store_true", help=argparse.SUPPRESS)
    problem_sub.add_parser("list", allow_abbrev=False)

    web_parser = add_parser(subparsers, "web")
    web_parser.add_argument(
        "web_action",
        nargs="?",
        choices=["start", "stop", "restart"],
        help="run in the background, stop it, or restart it; omit for foreground mode",
    )
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8765)
    web_open = web_parser.add_mutually_exclusive_group()
    web_open.add_argument("--open", dest="open", action="store_true", default=True)
    web_open.add_argument("--no-open", dest="open", action="store_false")
    web_parser.add_argument("--debug", action="store_true")
    web_parser.add_argument(
        "--allow-remote-run",
        action="store_true",
        help="allow run APIs when binding judge web to a non-local host",
    )
    web_parser.add_argument("--service-runner", help=argparse.SUPPRESS)

    studio_parser = add_parser(subparsers, "studio")
    add_studio_web_arguments(studio_parser)

    return parser
