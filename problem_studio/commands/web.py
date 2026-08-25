"""웹 CLI 명령의 인자 처리와 콘솔 출력을 담당합니다."""

from __future__ import annotations

import argparse
from pathlib import Path

from alj_core.web_service import (
    WebServiceSpec,
    has_saved_web_service,
    restart_web_service,
    start_web_service,
    stop_web_service,
)
from problem_studio.core.repositories import clone_problem_repository
from problem_studio.web.server import run_server

PROBLEM_STUDIO_WEB_SERVICE = WebServiceSpec(
    name="problem-studio-web",
    display_name="Problem Studio web",
    module="problem_studio",
    health_app="problem_studio",
)


def _child_args(
    workspace: Path,
    args: argparse.Namespace,
    active_repository: str | None,
) -> list[str]:
    command = [
        "--workspace",
        str(workspace),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--no-open",
    ]
    if active_repository:
        command.extend(["--repo", active_repository])
    return command


def _print_started(state: dict) -> None:
    print(f"Problem Studio web을 백그라운드에서 시작했습니다 (PID {state['pid']}).")
    print(f"URL: {state['url']}")
    print(f"로그: {state['logPath']}")


def handle(args: argparse.Namespace) -> int:
    """web CLI 명령의 옵션을 해석하고 필요한 서비스 호출과 출력 작업을 수행합니다.

    Args:
        args (argparse.Namespace): argparse가 파싱한 명령 옵션과 대상 값을 담은 네임스페이스입니다.

    Returns:
        int: 명령 성공 여부를 나타내는 프로세스 종료 코드입니다.
    """
    action = getattr(args, "web_action", None)
    if action == "stop":
        result = stop_web_service(PROBLEM_STUDIO_WEB_SERVICE)
        if result["status"] == "stopped":
            print(f"Problem Studio web을 종료했습니다 (PID {result['pid']}).")
        else:
            print("Problem Studio web은 실행 중이 아닙니다.")
            if result.get("unrelatedPid"):
                print(f"PID {result['unrelatedPid']}의 다른 프로세스는 종료하지 않았습니다.")
        return 0

    active_repository = args.repo
    reuse_saved = action == "restart" and has_saved_web_service(PROBLEM_STUDIO_WEB_SERVICE)
    if args.clone and not reuse_saved:
        summary = clone_problem_repository(args.workspace, args.clone, args.branch, args.repo_name)
        active_repository = summary["name"]
    workspace = Path(args.workspace).expanduser().resolve()
    if getattr(args, "service_runner", None):
        run_server(workspace, args.host, args.port, False, active_repository)
        return 0
    if action is None:
        run_server(workspace, args.host, args.port, args.open, active_repository)
        return 0

    service_args = _child_args(workspace, args, active_repository)
    if action == "restart":
        state = restart_web_service(
            PROBLEM_STUDIO_WEB_SERVICE,
            child_args=service_args,
            host=args.host,
            port=args.port,
            open_browser=args.open,
        )
    else:
        state = start_web_service(
            PROBLEM_STUDIO_WEB_SERVICE,
            child_args=service_args,
            host=args.host,
            port=args.port,
            open_browser=args.open,
        )
    _print_started(state)
    return 0
