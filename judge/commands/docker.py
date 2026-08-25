"""Signed Docker Judge launcher의 CLI 하위 명령을 처리합니다."""

from __future__ import annotations

import argparse

from judge.core.docker_launcher import (
    JUDGE_DOCKER_WEB,
    STUDIO_DOCKER_WEB,
    docker_web_status,
    restart_docker_studio_web,
    restart_docker_web,
    run_docker_studio_web,
    run_docker_web,
    setup_docker_judge,
    start_docker_studio_web,
    start_docker_web,
    stop_docker_studio_web,
    stop_docker_web,
)
from judge.core.errors import JudgeError


def _print_status(state: dict, spec=JUDGE_DOCKER_WEB) -> None:
    if not state.get("running"):
        status = state.get("status", "not-running")
        if status == "not-running":
            print(f"{spec.display_name}은 실행 중이 아닙니다.")
        else:
            print(f"{spec.display_name} 컨테이너가 정지 상태입니다 ({status}).")
        return
    health = "정상" if state.get("healthy") else "응답 없음"
    print(f"{spec.display_name}이 실행 중입니다 ({health}).")
    print(f"컨테이너: {state['container']}")
    print(f"로컬 URL: {state['url']}")
    print(f"외부 공개 포트: {state['publishedAddress']}")
    if state.get("workspace"):
        print(f"작업공간: {state['workspace']}")


def handle(args: argparse.Namespace) -> int:
    """Docker setup 또는 hardened web launcher를 host fallback 없이 실행합니다."""
    if args.docker_command == "setup":
        setup_docker_judge()
        return 0
    if args.docker_command == "web":
        action = args.docker_web_action
        if action == "status":
            _print_status(docker_web_status(JUDGE_DOCKER_WEB))
            return 0
        if action == "stop":
            state = stop_docker_web()
            if state["status"] == "stopped":
                print(f"Docker Judge web을 종료했습니다 ({state['container']}).")
            else:
                _print_status(state)
            return 0
        if action == "restart":
            _print_status(restart_docker_web(args.port))
            return 0
        port = args.port if args.port is not None else JUDGE_DOCKER_WEB.default_port
        if action == "start":
            _print_status(start_docker_web(port))
            return 0
        run_docker_web(port)
        return 0
    if args.docker_command == "studio":
        action = args.docker_web_action
        if action == "status":
            _print_status(docker_web_status(STUDIO_DOCKER_WEB), STUDIO_DOCKER_WEB)
            return 0
        if action == "stop":
            state = stop_docker_studio_web()
            if state["status"] == "stopped":
                print(f"Docker Problem Studio web을 종료했습니다 ({state['container']}).")
            else:
                _print_status(state, STUDIO_DOCKER_WEB)
            return 0
        if action == "restart":
            _print_status(
                restart_docker_studio_web(args.workspace, args.port),
                STUDIO_DOCKER_WEB,
            )
            return 0
        port = args.port if args.port is not None else STUDIO_DOCKER_WEB.default_port
        workspace = args.workspace or "."
        if action == "start":
            _print_status(
                start_docker_studio_web(workspace, port),
                STUDIO_DOCKER_WEB,
            )
            return 0
        run_docker_studio_web(workspace, port)
        return 0
    raise JudgeError(f"unknown docker command: {args.docker_command}")


__all__ = ["handle"]
