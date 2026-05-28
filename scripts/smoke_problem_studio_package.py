from __future__ import annotations

import argparse
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
from urllib.request import urlopen

ASSET_PATHS = [
    "/",
    "/static/app.js",
    "/static/styles.css",
    "/static/vendor/codemirror/codemirror.min.js",
    "/static/vendor/codemirror/keymap/vim.min.js",
    "/static/vendor/codemirror/mode/python/python.min.js",
]


def run_command(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print(f"+ {' '.join(command)}")
    subprocess.run(command, cwd=cwd, env=env, check=True)


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
            raise RuntimeError(
                f"problem-studio web exited early with {process.returncode}\n{output}"
            )
        try:
            with urlopen(base_url, timeout=1.5) as response:
                if response.status == 200:
                    return
        except URLError as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"timed out waiting for {base_url}: {last_error}")


def assert_asset(base_url: str, path: str) -> None:
    url = f"{base_url}{path}"
    with urlopen(url, timeout=3) as response:
        body = response.read()
        if response.status != 200:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        if not body:
            raise RuntimeError(f"{path} returned an empty response")
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

    with tempfile.TemporaryDirectory(prefix="alj-problem-studio-package-smoke-") as tmp_name:
        tmp_root = Path(tmp_name)
        dist_dir = tmp_root / "dist"
        venv_dir = tmp_root / "venv"
        workspace = tmp_root / "workspace"
        workspace.mkdir()

        run_command([uv, "build", "--out-dir", str(dist_dir)], cwd=repo_root)
        wheels = sorted(dist_dir.glob("*.whl"))
        sdists = sorted(dist_dir.glob("*.tar.gz"))
        if not wheels:
            raise RuntimeError("uv build did not produce a wheel")
        if not sdists:
            raise RuntimeError("uv build did not produce an sdist")

        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python = venv_bin(venv_dir, "python")
        run_command(
            [uv, "pip", "install", "--python", str(python), str(wheels[-1])],
            cwd=repo_root,
        )

        problem_studio = venv_bin(venv_dir, "problem-studio")
        port = find_free_port()
        base_url = f"http://127.0.0.1:{port}"
        process = subprocess.Popen(
            [
                str(problem_studio),
                "web",
                "--workspace",
                str(workspace),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--no-open",
            ],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            wait_for_server(base_url, process, timeout_seconds)
            for asset_path in ASSET_PATHS:
                assert_asset(base_url, asset_path)
        finally:
            terminate_process(process)

    print("Problem Studio package smoke passed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    try:
        smoke_package(repo_root, args.timeout)
    except Exception as exc:
        print(f"package smoke failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
