from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ACCEPTED_SOURCE = """\
import sys


def main():
    data = list(map(int, sys.stdin.read().split()))
    if not data:
        return
    n, m = data
    out = []
    used = [False] * (n + 1)

    def backtrack(seq):
        if len(seq) == m:
            out.append(" ".join(map(str, seq)))
            return
        for value in range(1, n + 1):
            if used[value]:
                continue
            used[value] = True
            seq.append(value)
            backtrack(seq)
            seq.pop()
            used[value] = False

    backtrack([])
    sys.stdout.write("\\n".join(out))
    if out:
        sys.stdout.write("\\n")


if __name__ == "__main__":
    main()
"""


def run_command(
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    print(f"+ {' '.join(command)}", flush=True)
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
        check=True,
    )


def venv_bin(venv_dir: Path, executable: str) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / executable
    return venv_dir / "bin" / executable


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(base_url: str, process: subprocess.Popen[str], timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output, _ = process.communicate(timeout=1)
            raise RuntimeError(f"judge web exited early with {process.returncode}\n{output}")
        try:
            with urlopen(base_url, timeout=1.5) as response:
                if response.status == 200:
                    return
        except URLError as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"timed out waiting for {base_url}: {last_error}")


def get_json(base_url: str, path: str) -> dict | list:
    with urlopen(f"{base_url}{path}", timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def post_json(base_url: str, path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def assert_static_asset(base_url: str, path: str) -> None:
    with urlopen(f"{base_url}{path}", timeout=5) as response:
        body = response.read()
        if response.status != 200 or not body:
            raise RuntimeError(f"{path} did not return a non-empty HTTP 200 response")
    print(f"verified {path} ({len(body)} bytes)")


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def smoke_package(repo_root: Path, timeout_seconds: float) -> None:
    uv = shutil.which(os.environ.get("UV", "uv"))
    if not uv:
        raise RuntimeError("uv executable was not found")

    with tempfile.TemporaryDirectory(prefix="alj-judge-web-package-smoke-") as tmp_name:
        tmp_root = Path(tmp_name)
        dist_dir = tmp_root / "dist"
        pack_dir = tmp_root / "packs-out"
        venv_dir = tmp_root / "venv"
        runtime = tmp_root / "runtime"
        empty_project = tmp_root / "empty-project"
        workspace = tmp_root / "web-workspace"
        for directory in (pack_dir, runtime, empty_project, workspace):
            directory.mkdir()

        run_command([uv, "build", "--out-dir", str(dist_dir)], cwd=repo_root)
        wheels = sorted(dist_dir.glob("*.whl"))
        if not wheels:
            raise RuntimeError("uv build did not produce a wheel")

        build_env = {
            **os.environ,
            "ALJ_CACHE_HOME": str(tmp_root / "build-cache"),
            "ALJ_DATA_HOME": str(tmp_root / "build-data"),
            "ALJ_PROJECT_ROOT": str(repo_root),
            "ALJ_PYTHON": sys.executable,
        }
        run_command(
            [
                sys.executable,
                "-m",
                "judge",
                "pack",
                "build",
                str(repo_root / "problems" / "06"),
                "--pack-id",
                "packaged-web-smoke",
                "--out",
                str(pack_dir),
                "--verify-profile",
                "sample",
            ],
            cwd=repo_root,
            env=build_env,
            capture=True,
        )
        archives = sorted(pack_dir.glob("packaged-web-smoke-*.aljpack"))
        if len(archives) != 1:
            raise RuntimeError(f"expected one pack archive, found {len(archives)}")

        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python = venv_bin(venv_dir, "python")
        run_command(
            [uv, "pip", "install", "--python", str(python), str(wheels[-1])],
            cwd=repo_root,
        )
        judge = venv_bin(venv_dir, "judge")
        run_env = {
            **os.environ,
            "ALJ_CACHE_HOME": str(runtime / "cache"),
            "ALJ_DATA_HOME": str(runtime / "data"),
            "ALJ_PACK_HOME": str(runtime / "packs"),
            "ALJ_SOURCE_HOME": str(runtime / "sources"),
            "ALJ_PROJECT_ROOT": str(empty_project),
            "ALJ_PYTHON": str(python),
        }
        run_command(
            [str(judge), "pack", "install", str(archives[0])],
            cwd=empty_project,
            env=run_env,
        )

        port = find_free_port()
        base_url = f"http://127.0.0.1:{port}"
        process = subprocess.Popen(
            [
                str(judge),
                "web",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-open",
            ],
            cwd=workspace,
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            wait_for_server(base_url, process, timeout_seconds)
            assert_static_asset(base_url, "/static/app.js")
            problems = get_json(base_url, "/api/problems")
            if not any(problem.get("problemId") == "06" for problem in problems):
                raise RuntimeError(f"installed pack problem not listed: {problems}")

            samples = get_json(base_url, "/api/problems/06/samples")
            if samples.get("profile") != "sample" or not samples.get("cases"):
                raise RuntimeError(f"sample generation did not return cases: {samples}")

            for profile in ("sample", "full"):
                result = post_json(
                    base_url,
                    "/api/run",
                    {
                        "problem_id": "06",
                        "profile": profile,
                        "source_mode": "text",
                        "filename": "main.py",
                        "source_text": ACCEPTED_SOURCE,
                    },
                )
                if result.get("status") != "accepted" or result.get("profile") != profile:
                    raise RuntimeError(f"{profile} run failed: {result}")
                print(f"verified {profile} run ({len(result.get('cases', []))} cases)")
        finally:
            terminate_process(process)

    print("judge Web package smoke passed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    try:
        smoke_package(repo_root, args.timeout)
    except Exception as exc:
        print(f"judge Web package smoke failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
