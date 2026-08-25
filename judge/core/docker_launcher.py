"""Signed official image를 사용하는 fail-closed Docker Judge launcher입니다."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

from judge import __version__
from judge.core.docker_runtime import ensure_sandbox_preflight
from judge.core.errors import JudgeError
from judge.core.pack_signatures import DEFAULT_GITHUB_OIDC_ISSUER, cosign_path

OFFICIAL_IMAGE_REPOSITORY = "ghcr.io/tony9402/algorithm-local-judge"
OFFICIAL_IMAGE = f"{OFFICIAL_IMAGE_REPOSITORY}:{__version__}"
OFFICIAL_IMAGE_IDENTITY = (
    "https://github.com/tony9402/algorithm-local-judge/"
    f".github/workflows/release.yml@refs/tags/v{__version__}"
)
COSIGN_VERIFIER_IMAGE = (
    "ghcr.io/sigstore/cosign/cosign:v3.0.6@"
    "sha256:de9c65609e6bde17e6b48de485ee788407c9502fa08b8f4459f595b21f56cd00"
)
OFFICIAL_PROBLEM_REPOSITORY = "tony9402/algorithm-package"
DATA_VOLUME = "algorithm-local-judge-data"
INTERNAL_NETWORK = "algorithm-local-judge-internal"
SETUP_CONTAINER = "algorithm-local-judge-setup"
WEB_CONTAINER = "algorithm-local-judge-web"
STUDIO_WEB_CONTAINER = "algorithm-local-judge-problem-studio-web"
MANAGED_LABEL_KEY = "io.algorithm-local-judge.managed"
MANAGED_LABEL = f"{MANAGED_LABEL_KEY}=true"
SERVICE_LABEL_KEY = "io.algorithm-local-judge.service"
PORT_LABEL_KEY = "io.algorithm-local-judge.port"
WORKSPACE_LABEL_KEY = "io.algorithm-local-judge.workspace"
CONTAINER_USER = "10001:10001"
CONTAINER_WEB_PORT = 8765
COMMAND_TIMEOUT_SECONDS = 300
WEB_START_TIMEOUT_SECONDS = 20.0
SETUP_MARKER = "/data/.alj-docker-setup-complete"
MINIMUM_DOCKER_ENGINE_MAJOR = 28
ISOLATED_GATEWAY_OPTION = "com.docker.network.bridge.gateway_mode_ipv4=isolated"


@dataclass(frozen=True)
class DockerWebSpec:
    service: str
    display_name: str
    container_name: str
    command: str
    health_app: str
    default_port: int
    requires_problem_pack: bool
    requires_workspace: bool = False


JUDGE_DOCKER_WEB = DockerWebSpec(
    service="judge-web",
    display_name="Docker Judge web",
    container_name=WEB_CONTAINER,
    command="judge",
    health_app="judge",
    default_port=8765,
    requires_problem_pack=True,
)
STUDIO_DOCKER_WEB = DockerWebSpec(
    service="problem-studio-web",
    display_name="Docker Problem Studio web",
    container_name=STUDIO_WEB_CONTAINER,
    command="problem-studio",
    health_app="problem_studio",
    default_port=8775,
    requires_problem_pack=False,
    requires_workspace=True,
)


def _command_error(result: subprocess.CompletedProcess[str]) -> str:
    detail = (result.stderr or result.stdout or "").strip()
    if not detail:
        return f"command exited with status {result.returncode}; see output above"
    if len(detail) > 2000:
        return f"{detail[:2000]}..."
    return detail


def _run_command(
    command: list[str],
    action: str,
    *,
    check: bool = True,
    capture_output: bool = True,
    timeout: int | None = COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise JudgeError(f"Docker {action} timed out") from exc
    except OSError as exc:
        raise JudgeError(f"Docker {action} could not start: {exc}") from exc
    if check and result.returncode != 0:
        raise JudgeError(f"Docker {action} failed: {_command_error(result)}")
    return result


def _inspect_image_digest() -> str:
    result = _run_command(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            "{{index .RepoDigests 0}}",
            OFFICIAL_IMAGE,
        ],
        "image inspection",
    )
    digest = result.stdout.strip()
    prefix = f"{OFFICIAL_IMAGE_REPOSITORY}@sha256:"
    checksum = digest.removeprefix(prefix)
    if not digest.startswith(prefix) or len(checksum) != 64:
        raise JudgeError(
            f"official Docker image did not resolve to a pinned RepoDigest: {digest or 'empty'}"
        )
    try:
        int(checksum, 16)
    except ValueError as exc:
        raise JudgeError(f"official Docker image has an invalid RepoDigest: {digest}") from exc
    return digest


def _verify_image_signature(digest: str) -> None:
    try:
        verifier = [cosign_path()]
    except JudgeError:
        verifier = ["docker", "run", "--rm", COSIGN_VERIFIER_IMAGE]
    _run_command(
        [
            *verifier,
            "verify",
            digest,
            "--certificate-identity",
            OFFICIAL_IMAGE_IDENTITY,
            "--certificate-oidc-issuer",
            DEFAULT_GITHUB_OIDC_ISSUER,
        ],
        "image signature verification",
    )


def pull_and_verify_official_image() -> str:
    """공식 version tag를 pull한 뒤 immutable digest의 release 서명을 검증합니다."""
    _run_command(["docker", "pull", OFFICIAL_IMAGE], "image pull")
    digest = _inspect_image_digest()
    _verify_image_signature(digest)
    return digest


def _ensure_launcher_preflight() -> None:
    _, diagnostics = ensure_sandbox_preflight("docker")
    version = str(diagnostics.get("serverVersion") or "")
    try:
        major = int(version.split(".", 1)[0])
    except ValueError as exc:
        raise JudgeError(
            f"could not determine Docker Engine version: {version or 'unknown'}"
        ) from exc
    if major < MINIMUM_DOCKER_ENGINE_MAJOR:
        raise JudgeError(
            f"Docker Engine {MINIMUM_DOCKER_ENGINE_MAJOR}+ is required for isolated gateway "
            f"protections; found {version}"
        )


def verify_local_official_image() -> str:
    """로컬 공식 이미지를 immutable digest로 해석하고 실행 전에 다시 서명 검증합니다."""
    try:
        digest = _inspect_image_digest()
    except JudgeError as exc:
        raise JudgeError(
            "official Docker image is not ready; run `judge docker setup` first"
        ) from exc
    _verify_image_signature(digest)
    return digest


def _setup_run_command(digest: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        SETUP_CONTAINER,
        "--network",
        "bridge",
        "--user",
        CONTAINER_USER,
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=256m",
        "--tmpfs",
        "/home/alj/.sigstore:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001,mode=0700",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--pids-limit",
        "256",
        "--memory",
        "2g",
        "--memory-swap",
        "2g",
        "--cpus",
        "2.0",
        "--mount",
        f"type=volume,source={DATA_VOLUME},target=/data",
        digest,
        "/bin/sh",
        "-c",
        f"mkdir -p /data/jobs && rm -f {SETUP_MARKER} "
        f'&& judge problem install "$1" --require-pack '
        f"&& touch {SETUP_MARKER}",
        "alj-docker-setup",
        OFFICIAL_PROBLEM_REPOSITORY,
    ]


def setup_docker_judge() -> str:
    """서명 검증된 이미지와 영속 data volume에 공식 문제 팩을 준비합니다."""
    _ensure_launcher_preflight()
    print(f"Pulling signed official image: {OFFICIAL_IMAGE}")
    digest = pull_and_verify_official_image()
    print(f"Verified official image: {digest}")
    _run_command(
        ["docker", "volume", "create", "--label", MANAGED_LABEL, DATA_VOLUME],
        "data volume creation",
    )
    _ensure_data_volume()
    print(f"Installing the official problem pack into Docker volume {DATA_VOLUME}...")
    _run_command(_setup_run_command(digest), "problem pack setup", capture_output=False)
    print("Docker Judge setup complete. Start it with `judge docker web start`.")
    return digest


def _ensure_data_volume() -> None:
    result = _run_command(
        [
            "docker",
            "volume",
            "inspect",
            "--format",
            f'{{{{index .Labels "{MANAGED_LABEL_KEY}"}}}}',
            DATA_VOLUME,
        ],
        "data volume inspection",
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise JudgeError("Docker Judge data is not initialized; run `judge docker setup` first")


def _ensure_setup_marker(digest: str) -> None:
    _run_command(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            CONTAINER_USER,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--pids-limit",
            "16",
            "--memory",
            "128m",
            "--cpus",
            "0.5",
            "--mount",
            f"type=volume,source={DATA_VOLUME},target=/data,readonly",
            digest,
            "/usr/bin/test",
            "-f",
            SETUP_MARKER,
        ],
        "setup completion check",
    )


def _ensure_internal_network() -> None:
    result = _run_command(
        [
            "docker",
            "network",
            "inspect",
            "--format",
            f'{{{{.Internal}}}} {{{{.Driver}}}} {{{{index .Labels "{MANAGED_LABEL_KEY}"}}}} '
            '{{index .Options "com.docker.network.bridge.gateway_mode_ipv4"}}',
            INTERNAL_NETWORK,
        ],
        "internal network inspection",
        check=False,
    )
    if result.returncode != 0:
        _run_command(
            [
                "docker",
                "network",
                "create",
                "--driver",
                "bridge",
                "--internal",
                "--opt",
                ISOLATED_GATEWAY_OPTION,
                "--label",
                MANAGED_LABEL,
                INTERNAL_NETWORK,
            ],
            "internal network creation",
        )
        return
    if result.stdout.strip() != "true bridge true isolated":
        raise JudgeError(
            f"refusing to use Docker network {INTERNAL_NETWORK}: "
            "expected a managed internal bridge network"
        )


def _validate_host_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise JudgeError("Docker web port must be between 1 and 65535")


def _workspace_path(workspace: str | Path | None) -> Path:
    resolved = Path("." if workspace is None else workspace).expanduser().resolve()
    if not resolved.is_dir():
        raise JudgeError(f"Problem Studio workspace directory not found: {resolved}")
    return resolved


def _web_run_command(
    digest: str,
    port: int,
    *,
    spec: DockerWebSpec = JUDGE_DOCKER_WEB,
    detached: bool = False,
    workspace: Path | None = None,
) -> list[str]:
    command = [
        "docker",
        "run",
        *(["--detach"] if detached else ["--rm"]),
        "--name",
        spec.container_name,
        "--label",
        MANAGED_LABEL,
        "--label",
        f"{SERVICE_LABEL_KEY}={spec.service}",
        "--label",
        f"{PORT_LABEL_KEY}={port}",
        "--network",
        INTERNAL_NETWORK,
        "--user",
        CONTAINER_USER,
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=256m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--pids-limit",
        "256",
        "--memory",
        "2g",
        "--memory-swap",
        "2g",
        "--cpus",
        "2.0",
    ]
    if spec.requires_workspace:
        if workspace is None:
            raise JudgeError("Problem Studio Docker web requires a workspace")
        command.extend(
            [
                "--label",
                f"{WORKSPACE_LABEL_KEY}={workspace}",
                "--mount",
                f"type=bind,source={workspace},target=/workspace",
                "--mount",
                f"type=volume,source={DATA_VOLUME},target=/data",
            ]
        )
    else:
        command.extend(
            [
                "--tmpfs",
                "/workspace:rw,noexec,nosuid,nodev,size=512m,uid=10001,gid=10001,mode=0700",
                "--mount",
                f"type=volume,source={DATA_VOLUME},target=/data,readonly",
                "--tmpfs",
                "/data/cache:rw,nosuid,nodev,size=1024m,uid=10001,gid=10001,mode=0700",
                "--tmpfs",
                "/data/jobs:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001,mode=0700",
            ]
        )
    command.extend(
        [
            "--publish",
            f"0.0.0.0:{port}:{port}",
            digest,
            spec.command,
            "web",
        ]
    )
    if spec.requires_workspace:
        command.extend(["--workspace", "/workspace"])
    command.extend(["--host", "0.0.0.0", "--port", str(port), "--no-open"])
    if spec is JUDGE_DOCKER_WEB:
        command.append("--allow-remote-run")
    else:
        command.append("--allow-remote-write")
    return command


def _ensure_or_create_data_volume() -> None:
    _run_command(
        ["docker", "volume", "create", "--label", MANAGED_LABEL, DATA_VOLUME],
        "data volume creation",
    )
    _ensure_data_volume()


def _prepare_web_service(spec: DockerWebSpec, digest: str) -> None:
    if spec.requires_problem_pack:
        _ensure_data_volume()
        _ensure_setup_marker(digest)
    else:
        _ensure_or_create_data_volume()
    _ensure_internal_network()


def _container_state(spec: DockerWebSpec) -> dict[str, Any] | None:
    result = _run_command(
        ["docker", "container", "inspect", spec.container_name],
        f"{spec.display_name} status inspection",
        check=False,
    )
    if result.returncode != 0:
        detail = _command_error(result).lower()
        if "no such" in detail or "not found" in detail:
            return None
        raise JudgeError(f"{spec.display_name} status inspection failed: {_command_error(result)}")
    try:
        payload = json.loads(result.stdout)
        container = payload[0]
        labels = container["Config"]["Labels"] or {}
        docker_state = container["State"]
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise JudgeError(f"{spec.display_name} returned invalid inspection data") from exc
    if labels.get(MANAGED_LABEL_KEY) != "true" or labels.get(SERVICE_LABEL_KEY) != spec.service:
        raise JudgeError(
            f"refusing to manage container {spec.container_name}: managed labels do not match. "
            "A legacy or unrelated container is using this name; stop it manually, then remove "
            "it if it remains before retrying"
        )
    try:
        port = int(labels[PORT_LABEL_KEY])
    except (KeyError, TypeError, ValueError) as exc:
        raise JudgeError(f"{spec.display_name} has an invalid saved port") from exc
    _validate_host_port(port)
    workspace = labels.get(WORKSPACE_LABEL_KEY)
    if spec.requires_workspace and (not isinstance(workspace, str) or not workspace):
        raise JudgeError(f"{spec.display_name} has an invalid saved workspace")
    running = bool(docker_state.get("Running"))
    status = "running" if running else str(docker_state.get("Status") or "stopped")
    return {
        "status": status,
        "running": running,
        "container": spec.container_name,
        "port": port,
        "url": f"http://127.0.0.1:{port}",
        "publishedAddress": f"0.0.0.0:{port}",
        "workspace": workspace,
    }


def _health_matches(spec: DockerWebSpec, port: int) -> bool:
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/healthz", timeout=0.5) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, TimeoutError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("app") == spec.health_app


def _wait_for_web_service(spec: DockerWebSpec, port: int) -> None:
    deadline = time.monotonic() + WEB_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _health_matches(spec, port):
            return
        state = _container_state(spec)
        if state is None or not state["running"]:
            logs = _run_command(
                ["docker", "logs", "--tail", "100", spec.container_name],
                f"{spec.display_name} logs",
                check=False,
            )
            detail = (logs.stderr or logs.stdout).strip()
            raise JudgeError(
                f"{spec.display_name} exited before becoming ready"
                + (f": {detail}" if detail else "")
            )
        time.sleep(0.2)
    raise JudgeError(
        f"{spec.display_name} did not become ready within {WEB_START_TIMEOUT_SECONDS:g} seconds"
    )


def docker_web_status(spec: DockerWebSpec = JUDGE_DOCKER_WEB) -> dict[str, Any]:
    state = _container_state(spec)
    if state is None:
        return {"status": "not-running", "running": False, "container": spec.container_name}
    state["healthy"] = state["running"] and _health_matches(spec, int(state["port"]))
    return state


def _remove_stopped_container(spec: DockerWebSpec, state: dict[str, Any] | None) -> None:
    if state is None:
        return
    if state["running"]:
        raise JudgeError(
            f"{spec.display_name} is already running at {state['url']} "
            f"(container {spec.container_name})"
        )
    _run_command(["docker", "rm", spec.container_name], f"{spec.display_name} container removal")


def _start_web_service(
    spec: DockerWebSpec,
    *,
    port: int,
    workspace: str | Path | None = None,
    detached: bool,
) -> dict[str, Any] | None:
    _validate_host_port(port)
    resolved_workspace = _workspace_path(workspace) if spec.requires_workspace else None
    existing = _container_state(spec)
    _remove_stopped_container(spec, existing)
    _ensure_launcher_preflight()
    digest = verify_local_official_image()
    _prepare_web_service(spec, digest)
    print(f"{spec.display_name} starting at http://127.0.0.1:{port}")
    print(f"Published on all host interfaces: 0.0.0.0:{port}")
    result = _run_command(
        _web_run_command(
            digest,
            port,
            spec=spec,
            detached=detached,
            workspace=resolved_workspace,
        ),
        f"{spec.display_name} container",
        capture_output=detached,
        timeout=COMMAND_TIMEOUT_SECONDS if detached else None,
    )
    if not detached:
        return None
    _wait_for_web_service(spec, port)
    return {
        "status": "running",
        "running": True,
        "healthy": True,
        "container": spec.container_name,
        "containerId": result.stdout.strip(),
        "port": port,
        "url": f"http://127.0.0.1:{port}",
        "publishedAddress": f"0.0.0.0:{port}",
        "workspace": str(resolved_workspace) if resolved_workspace else None,
    }


def _stop_web_service(spec: DockerWebSpec) -> dict[str, Any]:
    state = _container_state(spec)
    if state is None:
        return {"status": "not-running", "running": False, "container": spec.container_name}
    if not state["running"]:
        return state
    _run_command(
        ["docker", "stop", "--time", "10", spec.container_name],
        f"{spec.display_name} container stop",
    )
    return {**state, "status": "stopped", "running": False, "healthy": False}


def _restart_web_service(
    spec: DockerWebSpec,
    *,
    port: int | None,
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    state = _container_state(spec)
    resolved_port = (
        port if port is not None else (int(state["port"]) if state else spec.default_port)
    )
    resolved_workspace: str | Path | None = workspace
    if spec.requires_workspace and resolved_workspace is None and state is not None:
        resolved_workspace = state.get("workspace")
    _validate_host_port(resolved_port)
    if spec.requires_workspace:
        resolved_workspace = _workspace_path(resolved_workspace)
    if state is not None:
        if state["running"]:
            _run_command(
                ["docker", "stop", "--time", "10", spec.container_name],
                f"{spec.display_name} container stop",
            )
        _run_command(
            ["docker", "rm", spec.container_name],
            f"{spec.display_name} container removal",
        )
    started = _start_web_service(
        spec,
        port=resolved_port,
        workspace=resolved_workspace,
        detached=True,
    )
    assert started is not None
    return started


def run_docker_web(port: int = CONTAINER_WEB_PORT) -> None:
    """외부 egress가 없는 hardened 컨테이너에서 Judge UI를 전면 실행합니다."""
    _start_web_service(JUDGE_DOCKER_WEB, port=port, detached=False)


def start_docker_web(port: int = CONTAINER_WEB_PORT) -> dict[str, Any]:
    started = _start_web_service(JUDGE_DOCKER_WEB, port=port, detached=True)
    assert started is not None
    return started


def stop_docker_web() -> dict[str, Any]:
    return _stop_web_service(JUDGE_DOCKER_WEB)


def restart_docker_web(port: int | None = None) -> dict[str, Any]:
    return _restart_web_service(JUDGE_DOCKER_WEB, port=port)


def run_docker_studio_web(workspace: str | Path, port: int = 8775) -> None:
    _start_web_service(
        STUDIO_DOCKER_WEB,
        port=port,
        workspace=workspace,
        detached=False,
    )


def start_docker_studio_web(workspace: str | Path, port: int = 8775) -> dict[str, Any]:
    started = _start_web_service(
        STUDIO_DOCKER_WEB,
        port=port,
        workspace=workspace,
        detached=True,
    )
    assert started is not None
    return started


def stop_docker_studio_web() -> dict[str, Any]:
    return _stop_web_service(STUDIO_DOCKER_WEB)


def restart_docker_studio_web(
    workspace: str | Path | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    return _restart_web_service(STUDIO_DOCKER_WEB, port=port, workspace=workspace)


__all__ = [
    "COSIGN_VERIFIER_IMAGE",
    "DATA_VOLUME",
    "DockerWebSpec",
    "INTERNAL_NETWORK",
    "JUDGE_DOCKER_WEB",
    "MANAGED_LABEL",
    "MANAGED_LABEL_KEY",
    "OFFICIAL_IMAGE",
    "OFFICIAL_IMAGE_IDENTITY",
    "OFFICIAL_IMAGE_REPOSITORY",
    "OFFICIAL_PROBLEM_REPOSITORY",
    "PORT_LABEL_KEY",
    "SERVICE_LABEL_KEY",
    "STUDIO_DOCKER_WEB",
    "STUDIO_WEB_CONTAINER",
    "WORKSPACE_LABEL_KEY",
    "docker_web_status",
    "pull_and_verify_official_image",
    "restart_docker_studio_web",
    "restart_docker_web",
    "run_docker_web",
    "run_docker_studio_web",
    "setup_docker_judge",
    "start_docker_studio_web",
    "start_docker_web",
    "stop_docker_studio_web",
    "stop_docker_web",
    "verify_local_official_image",
]
