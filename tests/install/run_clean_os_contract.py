"""Run the published native install lifecycle on a disposable clean-OS runner."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError

ROOT = Path(__file__).resolve().parents[2]
TARGET_CHANNELS = {
    "macos-arm64": "macos",
    "macos-amd64": "macos",
    "ubuntu-amd64": "ubuntu-debian",
    "debian-amd64": "ubuntu-debian",
    "fedora-amd64": "fedora",
    "windows-amd64": "windows",
}
LANGUAGE_FILES = {
    "cpp": "main.cpp",
    "python": "main.py",
    "pypy": "main.pypy.py",
    "java": "Main.java",
}


def load_channel(path: Path, target: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise JudgeError(f"install channel state is invalid: {exc}") from exc
    channel_id = TARGET_CHANNELS[target]
    channel = (payload.get("channels") or {}).get(channel_id)
    if not isinstance(channel, dict):
        raise JudgeError(f"install channel is missing for {target}")
    if channel.get("status") != "published":
        raise JudgeError(
            f"clean-OS stable gate blocked: {channel_id} channel is not published; "
            "no install command was executed"
        )
    required = (
        "smokeInstallCommands",
        "upgradeCommand",
        "rollbackCommand",
        "uninstallCommand",
        "releaseVersion",
        "rollbackVersion",
        "sampleProblem",
        "samples",
    )
    missing = [name for name in required if not channel.get(name)]
    if missing:
        raise JudgeError(f"clean-OS lifecycle contract is incomplete: {', '.join(missing)}")
    commands = channel["smokeInstallCommands"]
    if not isinstance(commands, list) or not 1 <= len(commands) <= 3:
        raise JudgeError("clean-OS install must use 1 to 3 commands")
    samples = channel["samples"]
    if not isinstance(samples, dict) or set(samples) != set(LANGUAGE_FILES):
        raise JudgeError("clean-OS contract requires C++, Python, PyPy, and Java samples")
    return channel


def run_shell(command: str, environment: dict[str, str]) -> None:
    result = subprocess.run(
        command,
        shell=True,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        raise JudgeError(
            f"install lifecycle command failed ({command}):\n{result.stdout}\n{result.stderr}"
        )


def run_command(command: list[str], environment: dict[str, str]) -> str:
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        raise JudgeError(
            f"install lifecycle command failed ({' '.join(command)}):\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def assert_versions(environment: dict[str, str], expected: str) -> None:
    judge_version = run_command(["judge", "--version"], environment)
    studio_version = run_command(["problem-studio", "--version"], environment)
    if expected not in judge_version or expected not in studio_version:
        raise JudgeError(
            "launcher version mismatch: "
            f"expected={expected} judge={judge_version.strip()} studio={studio_version.strip()}"
        )


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def wait_ready(url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise JudgeError(f"web process exited before readiness: {url}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    raise JudgeError(f"readiness endpoint timed out: {url}")


def verify_readyz(environment: dict[str, str], workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    judge_port = available_port()
    studio_port = available_port()
    processes = [
        subprocess.Popen(
            ["judge", "web", "--no-open", "--port", str(judge_port)],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        ),
        subprocess.Popen(
            [
                "problem-studio",
                "web",
                "--workspace",
                str(workspace),
                "--no-open",
                "--port",
                str(studio_port),
            ],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        ),
    ]
    try:
        wait_ready(f"http://127.0.0.1:{judge_port}/readyz", processes[0])
        wait_ready(f"http://127.0.0.1:{studio_port}/readyz", processes[1])
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def verify_language_samples(
    channel: dict[str, Any],
    environment: dict[str, str],
    workspace: Path,
) -> None:
    source_root = workspace / "language-samples"
    source_root.mkdir(parents=True, exist_ok=True)
    for language, filename in LANGUAGE_FILES.items():
        source = source_root / filename
        source.write_text(channel["samples"][language], encoding="utf-8")
        run_command(
            [
                "judge",
                "run",
                "--problem",
                channel["sampleProblem"],
                "--language",
                language,
                str(source),
            ],
            environment,
        )


def run_lifecycle(target: str, channel_state: Path, work_root: Path) -> dict[str, Any]:
    channel = load_channel(channel_state, target)
    environment = os.environ.copy()
    data_home = work_root / "data"
    environment.update(
        {
            "ALJ_DATA_HOME": str(data_home),
            "ALJ_CACHE_HOME": str(work_root / "cache"),
            "ALJ_TOOLCHAIN_HOME": str(work_root / "toolchains"),
            "ALJ_PACK_HOME": str(data_home / "problem-packs"),
            "ALJ_SOURCE_HOME": str(data_home / "problem-sources"),
        }
    )
    for command in channel["smokeInstallCommands"]:
        run_shell(command, environment)
    assert_versions(environment, channel["rollbackVersion"])
    run_command(["judge", "setup", "--yes", "--no-web"], environment)
    marker = data_home / "install-smoke-preserve.marker"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("preserve\n", encoding="utf-8")
    verify_readyz(environment, work_root / "studio-workspace")
    verify_language_samples(channel, environment, work_root)

    run_shell(channel["upgradeCommand"], environment)
    assert_versions(environment, channel["releaseVersion"])
    if marker.read_text(encoding="utf-8") != "preserve\n":
        raise JudgeError("user data was not preserved across upgrade")

    run_shell(channel["rollbackCommand"], environment)
    assert_versions(environment, channel["rollbackVersion"])
    if marker.read_text(encoding="utf-8") != "preserve\n":
        raise JudgeError("user data was not preserved across rollback")

    run_shell(channel["uninstallCommand"], environment)
    if shutil.which("judge", path=environment.get("PATH")) is not None:
        raise JudgeError("judge command remains on PATH after uninstall")
    if marker.read_text(encoding="utf-8") != "preserve\n":
        raise JudgeError("uninstall removed user data")
    return {
        "schemaVersion": 1,
        "target": target,
        "installedVersion": channel["rollbackVersion"],
        "upgradedVersion": channel["releaseVersion"],
        "rolledBackVersion": channel["rollbackVersion"],
        "checks": [
            "judge-version",
            "problem-studio-version",
            "setup",
            "judge-readyz",
            "problem-studio-readyz",
            "cpp",
            "python",
            "pypy",
            "java",
            "upgrade",
            "rollback",
            "uninstall",
            "data-preserved",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=sorted(TARGET_CHANNELS), required=True)
    parser.add_argument(
        "--channels",
        type=Path,
        default=ROOT / "packaging" / "install-channels.json",
    )
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--attestation", type=Path)
    args = parser.parse_args()
    try:
        if args.work_root is not None:
            args.work_root.mkdir(parents=True, exist_ok=True)
            attestation = run_lifecycle(
                args.target,
                args.channels.resolve(),
                args.work_root.resolve(),
            )
        else:
            with tempfile.TemporaryDirectory(prefix="alj-clean-os-") as temporary:
                attestation = run_lifecycle(args.target, args.channels.resolve(), Path(temporary))
        if args.attestation is not None:
            args.attestation.parent.mkdir(parents=True, exist_ok=True)
            args.attestation.write_text(
                json.dumps(attestation, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except (JudgeError, OSError) as exc:
        print(f"error: {exc}")
        return 1
    print(f"Clean-OS install lifecycle passed: {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
