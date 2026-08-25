"""웹 CLI 명령의 인자 처리와 콘솔 출력을 담당합니다."""

from __future__ import annotations

import argparse

from alj_core.web_service import (
    WebServiceSpec,
    restart_web_service,
    start_web_service,
    stop_web_service,
    web_service_status,
)
from judge.web.server import run_server

JUDGE_WEB_SERVICE = WebServiceSpec(
    name="judge-web",
    display_name="Judge web",
    module="judge",
    health_app="judge",
)
DEFAULT_JUDGE_WEB_PORT = 8765


def _child_args(args: argparse.Namespace) -> list[str]:
    command = ["--host", args.host, "--port", str(args.port), "--no-open"]
    if args.debug:
        command.append("--debug")
    if args.allow_remote_run:
        command.append("--allow-remote-run")
    if args.allow_remote_write:
        command.append("--allow-remote-write")
    return command


def _print_started(state: dict) -> None:
    print(f"Judge web을 백그라운드에서 시작했습니다 (PID {state['pid']}).")
    print(f"URL: {state['url']}")
    print(f"로그: {state['logPath']}")


def _print_status(state: dict) -> None:
    if state["status"] != "running":
        print("Judge web은 실행 중이 아닙니다.")
        if state.get("unrelatedPid"):
            print(
                f"PID {state['unrelatedPid']}의 다른 프로세스는 Judge web으로 취급하지 않습니다."
            )
        return
    health = "정상" if state["healthy"] else "응답 없음"
    print(f"Judge web이 실행 중입니다 (PID {state['pid']}, {health}).")
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
    requested_port = args.port
    port = requested_port if requested_port is not None else DEFAULT_JUDGE_WEB_PORT
    if getattr(args, "service_runner", None):
        run_server(
            args.host,
            port,
            False,
            args.debug,
            args.allow_remote_run,
            args.allow_remote_write,
        )
        return 0
    if action is None:
        run_server(
            args.host,
            port,
            args.open,
            args.debug,
            args.allow_remote_run,
            args.allow_remote_write,
        )
        return 0
    if action == "status":
        _print_status(web_service_status(JUDGE_WEB_SERVICE))
        return 0
    if action == "stop":
        result = stop_web_service(JUDGE_WEB_SERVICE)
        if result["status"] == "stopped":
            print(f"Judge web을 종료했습니다 (PID {result['pid']}).")
        else:
            print("Judge web은 실행 중이 아닙니다.")
            if result.get("unrelatedPid"):
                print(f"PID {result['unrelatedPid']}의 다른 프로세스는 종료하지 않았습니다.")
        return 0

    args.port = port
    service_args = _child_args(args)
    if action == "restart":
        state = restart_web_service(
            JUDGE_WEB_SERVICE,
            child_args=service_args,
            host=args.host,
            port=port,
            open_browser=args.open,
            port_override=requested_port,
        )
    else:
        state = start_web_service(
            JUDGE_WEB_SERVICE,
            child_args=service_args,
            host=args.host,
            port=port,
            open_browser=args.open,
        )
    _print_started(state)
    return 0
