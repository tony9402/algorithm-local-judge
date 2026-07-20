"""빌드된 wheel과 sdist를 임시 가상환경에 설치한 뒤 Problem Studio 웹 정적 자산이 패키지에서 정상 제공되는지 검증하는 스모크 스크립트입니다."""

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
    "/readyz",
    "/static/app.js",
    "/static/styles.css",
    "/static/vendor/codemirror/codemirror.min.js",
    "/static/vendor/codemirror/keymap/vim.min.js",
    "/static/vendor/codemirror/mode/python/python.min.js",
]


def run_command(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    """패키지 스모크 과정에서 필요한 외부 명령을 실행하고 실패를 즉시 전파합니다.

    Args:
        command (list[str]): 실행할 명령과 인자 목록입니다.
        cwd (Path): 명령을 실행할 작업 디렉터리입니다.
        env (dict[str, str] | None): 명령 실행에 사용할 환경 변수입니다.
    """
    print(f"+ {' '.join(command)}")
    subprocess.run(command, cwd=cwd, env=env, check=True)


def venv_bin(venv_dir: Path, executable: str) -> Path:
    """운영체제별 가상환경 스크립트 디렉터리 규칙에 맞춰 실행 파일 경로를 구성합니다.

    Args:
        venv_dir (Path): 명령을 설치한 가상환경 루트 디렉터리입니다.
        executable (str): 찾을 실행 파일 이름입니다.

    Returns:
        Path: 가상환경 안의 실행 파일 경로입니다.
    """
    if os.name == "nt":
        return venv_dir / "Scripts" / executable
    return venv_dir / "bin" / executable


def find_free_port() -> int:
    """웹 서버 스모크 테스트가 충돌 없이 바인딩할 수 있는 로컬 TCP 포트를 찾습니다.

    Returns:
        int: 현재 호스트에서 사용할 수 있는 임시 포트 번호입니다.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(base_url: str, process: subprocess.Popen[str], timeout_seconds: float) -> None:
    """시작한 Problem Studio 웹 서버가 HTTP 200 응답을 낼 때까지 재시도하고, 조기 종료나 타임아웃은 명확한 오류로 보고합니다.

    Args:
        base_url (str): 준비 상태를 확인할 Problem Studio 웹 서버 기준 주소입니다.
        process (subprocess.Popen[str]): 실행 중인 웹 서버 프로세스입니다.
        timeout_seconds (float): 서버 준비를 기다릴 최대 초 단위 시간입니다.
    """
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
    """패키징된 Problem Studio 정적 자산이 HTTP 200과 비어 있지 않은 본문으로 제공되는지 확인합니다.

    Args:
        base_url (str): 정적 자산 요청을 보낼 서버 기준 주소입니다.
        path (str): 확인할 정적 자산 경로입니다.
    """
    url = f"{base_url}{path}"
    with urlopen(url, timeout=3) as response:
        body = response.read()
        if response.status != 200:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        if not body:
            raise RuntimeError(f"{path} returned an empty response")
    print(f"verified {path} ({len(body)} bytes)")


def terminate_process(process: subprocess.Popen[str]) -> None:
    """스모크 테스트가 띄운 웹 서버 프로세스를 정상 종료하고, 제한 시간 안에 끝나지 않으면 강제 종료합니다.

    Args:
        process (subprocess.Popen[str]): 종료할 웹 서버 프로세스입니다.
    """
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def smoke_package(repo_root: Path, timeout_seconds: float) -> None:
    """wheel과 sdist 빌드, 새 가상환경 설치, Problem Studio 웹 서버 실행, 정적 자산 검증까지 패키지 사용자 경로를 순서대로 확인합니다.

    Args:
        repo_root (Path): 빌드와 설치 명령을 실행할 저장소 루트입니다.
        timeout_seconds (float): 웹 서버 준비를 기다릴 최대 초 단위 시간입니다.
    """
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

        launchers = [
            ("problem-studio web", [str(venv_bin(venv_dir, "problem-studio")), "web"]),
            ("judge studio", [str(venv_bin(venv_dir, "judge")), "studio"]),
        ]
        for label, launcher in launchers:
            port = find_free_port()
            base_url = f"http://127.0.0.1:{port}"
            process = subprocess.Popen(
                [
                    *launcher,
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
            print(f"verified launcher: {label}")

    print("Problem Studio package smoke passed")


def main(argv: list[str] | None = None) -> int:
    """명령줄 인자를 읽어 Problem Studio 패키지 스모크 검증을 실행하고 실패 시 오류를 표준 오류에 출력합니다.

    Args:
        argv (list[str] | None): 테스트나 호출자가 전달할 명령줄 인자 목록입니다. 생략하면 실제 프로세스 인자를 사용합니다.

    Returns:
        int: 스모크 검증이 성공하면 0, 실패하면 1입니다.
    """
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
