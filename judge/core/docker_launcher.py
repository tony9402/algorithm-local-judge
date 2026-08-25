"""Signed official image를 사용하는 fail-closed Docker Judge launcher입니다."""

from __future__ import annotations

import subprocess

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
MANAGED_LABEL_KEY = "io.algorithm-local-judge.managed"
MANAGED_LABEL = f"{MANAGED_LABEL_KEY}=true"
CONTAINER_USER = "10001:10001"
CONTAINER_WEB_PORT = 8765
COMMAND_TIMEOUT_SECONDS = 300
SETUP_MARKER = "/data/.alj-docker-setup-complete"
MINIMUM_DOCKER_ENGINE_MAJOR = 28
ISOLATED_GATEWAY_OPTION = "com.docker.network.bridge.gateway_mode_ipv4=isolated"


def _command_error(result: subprocess.CompletedProcess[str]) -> str:
    detail = (result.stderr or result.stdout or "unknown error").strip()
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
            f"and loopback publishing protections; found {version}"
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
    print("Docker Judge setup complete. Start it with `judge docker web`.")
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


def _web_run_command(digest: str, port: int) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        WEB_CONTAINER,
        "--network",
        INTERNAL_NETWORK,
        "--user",
        CONTAINER_USER,
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=256m",
        "--tmpfs",
        "/workspace:rw,noexec,nosuid,nodev,size=512m,uid=10001,gid=10001,mode=0700",
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
        f"type=volume,source={DATA_VOLUME},target=/data,readonly",
        "--tmpfs",
        "/data/cache:rw,nosuid,nodev,size=1024m,uid=10001,gid=10001,mode=0700",
        "--tmpfs",
        "/data/jobs:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001,mode=0700",
        "--publish",
        f"127.0.0.1:{port}:{CONTAINER_WEB_PORT}",
        digest,
        "judge",
        "web",
        "--host",
        "0.0.0.0",
        "--port",
        str(CONTAINER_WEB_PORT),
        "--no-open",
        "--allow-remote-run",
    ]


def run_docker_web(port: int = CONTAINER_WEB_PORT) -> None:
    """외부 egress가 없는 hardened 컨테이너에서 loopback 전용 웹 UI를 실행합니다."""
    _validate_host_port(port)
    _ensure_launcher_preflight()
    digest = verify_local_official_image()
    _ensure_data_volume()
    _ensure_setup_marker(digest)
    _ensure_internal_network()
    print(f"Docker Judge UI starting at http://127.0.0.1:{port}")
    print("The web container uses an internal network with external egress disabled.")
    _run_command(
        _web_run_command(digest, port),
        "web container",
        capture_output=False,
        timeout=None,
    )


__all__ = [
    "COSIGN_VERIFIER_IMAGE",
    "DATA_VOLUME",
    "INTERNAL_NETWORK",
    "MANAGED_LABEL",
    "MANAGED_LABEL_KEY",
    "OFFICIAL_IMAGE",
    "OFFICIAL_IMAGE_IDENTITY",
    "OFFICIAL_IMAGE_REPOSITORY",
    "OFFICIAL_PROBLEM_REPOSITORY",
    "pull_and_verify_official_image",
    "run_docker_web",
    "setup_docker_judge",
    "verify_local_official_image",
]
