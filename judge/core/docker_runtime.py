"""Docker CLI와 daemon 준비 상태를 진단하고 명시적 sandbox preflight를 강제합니다."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError

DOCKER_INFO_TIMEOUT_SECONDS = 3.0
SANDBOX_MODE_ENV = "ALJ_SANDBOX_MODE"
SUPPORTED_SANDBOX_MODES = {"off", "docker"}


def docker_install_hint(system: str | None = None) -> str:
    """현재 운영체제에 맞는 공식 Docker 설치 안내를 반환합니다."""
    operating_system = system or platform.system()
    if operating_system == "Darwin":
        return (
            "Install and open Docker Desktop for Mac: "
            "https://docs.docker.com/desktop/setup/install/mac-install/"
        )
    if operating_system == "Linux":
        return (
            "Install Docker Engine for your Linux distribution: "
            "https://docs.docker.com/engine/install/"
        )
    if operating_system == "Windows":
        return (
            "Install and open Docker Desktop for Windows: "
            "https://docs.docker.com/desktop/setup/install/windows-install/"
        )
    return "Install Docker for this platform: https://docs.docker.com/engine/install/"


def docker_daemon_hint(system: str | None = None) -> str:
    """Docker CLI는 있지만 daemon에 연결할 수 없을 때의 복구 안내를 반환합니다."""
    operating_system = system or platform.system()
    if operating_system == "Darwin":
        return (
            "Open Docker Desktop or start the configured Docker-compatible daemon "
            "(for example, Colima), then wait until the engine is running."
        )
    if operating_system == "Linux":
        return (
            "Start Docker with `sudo systemctl start docker`; if it is already running, "
            "check the current user's Docker socket permission."
        )
    if operating_system == "Windows":
        return "Open Docker Desktop and wait until the Docker engine is running."
    return "Start the Docker daemon and check permission to access its socket."


def _compact_error(stderr: str, stdout: str) -> str:
    message = stderr.strip() or stdout.strip() or "docker info exited with a non-zero status"
    if len(message) > 500:
        return f"...{message[-500:]}"
    return message


def collect_docker_diagnostics() -> dict[str, Any]:
    """Docker CLI 탐지와 daemon 연결 검사를 하나의 안정적인 진단 결과로 만듭니다."""
    docker_path = shutil.which("docker")
    if not docker_path:
        return {
            "label": "Docker runtime",
            "status": "missing",
            "path": None,
            "env": None,
            "configured": None,
            "candidates": ["docker"],
            "cliStatus": "missing",
            "daemonStatus": "not_checked",
            "serverVersion": None,
            "error": "Docker CLI was not found on PATH.",
            "installHint": docker_install_hint(),
            "sandboxReady": False,
        }

    try:
        result = subprocess.run(
            [docker_path, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=DOCKER_INFO_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        error = f"docker info timed out after {DOCKER_INFO_TIMEOUT_SECONDS:g} seconds."
    except OSError as exc:
        error = f"docker info could not start: {exc}"
    else:
        if result.returncode == 0:
            return {
                "label": "Docker runtime",
                "status": "ok",
                "path": str(Path(docker_path)),
                "env": None,
                "configured": None,
                "candidates": ["docker"],
                "cliStatus": "ok",
                "daemonStatus": "running",
                "serverVersion": result.stdout.strip() or None,
                "error": None,
                "installHint": "",
                "sandboxReady": True,
            }
        error = _compact_error(result.stderr, result.stdout)

    return {
        "label": "Docker runtime",
        "status": "unavailable",
        "path": str(Path(docker_path)),
        "env": None,
        "configured": None,
        "candidates": ["docker"],
        "cliStatus": "ok",
        "daemonStatus": "unavailable",
        "serverVersion": None,
        "error": error,
        "installHint": docker_daemon_hint(),
        "sandboxReady": False,
    }


def sandbox_mode(value: str | None = None) -> str:
    """명시적 sandbox preflight 모드를 환경 변수 또는 전달값에서 해석합니다."""
    raw_value = os.environ.get(SANDBOX_MODE_ENV, "off") if value is None else value
    mode = raw_value.strip().lower()
    if mode not in SUPPORTED_SANDBOX_MODES:
        supported = ", ".join(sorted(SUPPORTED_SANDBOX_MODES))
        raise JudgeError(f"invalid {SANDBOX_MODE_ENV}={raw_value!r}; supported modes: {supported}")
    return mode


def ensure_sandbox_preflight(
    value: str | None = None,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """명시적 Docker 모드에서 준비되지 않은 실행을 host fallback 없이 차단합니다."""
    mode = sandbox_mode(value)
    docker = diagnostics if diagnostics is not None else collect_docker_diagnostics()
    if mode == "docker" and not docker["sandboxReady"]:
        reason = docker.get("error") or "Docker is not ready."
        hint = docker.get("installHint") or docker_install_hint()
        raise JudgeError(
            f"{SANDBOX_MODE_ENV}=docker requires a reachable Docker daemon, but the "
            f"preflight failed: {reason} Refusing to start without the requested isolation "
            f"(fail closed). {hint}"
        )
    return mode, docker
