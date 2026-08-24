"""빌드된 wheel을 임시 가상환경에 설치한 뒤 judge 웹 패키지 설치와 실행 흐름을 실제 HTTP 경계에서 검증하는 스모크 스크립트입니다."""

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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ACCEPTED_SOURCE = """\
import sys


def main():
    value = sys.stdin.read().strip()
    if value:
        print(value)


if __name__ == "__main__":
    main()
"""

GENERATOR_CPP = """#include "testlib.h"
#include <iostream>

int main(int argc, char* argv[]) {
    registerGen(argc, argv, 1);
    int n = opt<int>("n", 1);
    std::cout << n << "\\n";
    return 0;
}
"""

VALIDATOR_CPP = """#include "testlib.h"

int main(int argc, char* argv[]) {
    registerValidation(argc, argv);
    inf.readInt(1, 1000000, "n");
    inf.readEoln();
    inf.readEof();
    return 0;
}
"""

CHECKER_CPP = """#include "testlib.h"

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    int expected = ans.readInt();
    int actual = ouf.readInt();
    if (expected != actual) {
        quitf(_wa, "expected %d, got %d", expected, actual);
    }
    quitf(_ok, "accepted");
}
"""

SOLUTION_CPP = """#include <iostream>

int main() {
    int n;
    std::cin >> n;
    std::cout << n << "\\n";
    return 0;
}
"""

CASES_YML = """profiles:
  sample:
    cases:
      - name: sample-1
        type: fixed
        content: |
          1
  hidden:
    cases:
      - matrix:
          vars:
            n:
              range:
                from: 1
                to: 3
          item:
            name: "hidden-${n}"
            type: generator
            seed: "${n}"
            args:
              n: "${n}"
"""

SMOKE_COMPILE_TIMEOUT_MS = 30_000


def run_command(
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    """패키지 스모크 과정에서 필요한 외부 명령을 실행하고, 필요하면 출력을 캡처합니다.

    Args:
        command (list[str]): 실행할 명령과 인자 목록입니다.
        cwd (Path): 명령을 실행할 작업 디렉터리입니다.
        env (dict[str, str] | None): 명령 실행에 사용할 환경 변수입니다.
        capture (bool): 표준 출력과 표준 오류를 캡처할지 여부입니다.

    Returns:
        subprocess.CompletedProcess[str]: 실행이 성공한 하위 프로세스 결과 객체입니다.
    """
    print(f"+ {' '.join(command)}", flush=True)
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=capture,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        if not capture:
            raise
        raise RuntimeError(
            "command failed\n"
            f"command: {' '.join(command)}\n"
            f"exit: {exc.returncode}\n"
            f"stdout:\n{exc.stdout or ''}\n"
            f"stderr:\n{exc.stderr or ''}"
        ) from exc


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
    """시작한 judge 웹 서버가 HTTP 200 응답을 낼 때까지 재시도하고, 조기 종료나 타임아웃은 명확한 오류로 보고합니다.

    Args:
        base_url (str): 준비 상태를 확인할 judge 웹 서버 기준 주소입니다.
        process (subprocess.Popen[str]): 실행 중인 웹 서버 프로세스입니다.
        timeout_seconds (float): 서버 준비를 기다릴 최대 초 단위 시간입니다.
    """
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
    """스모크 검증 대상 API를 GET으로 호출하고 JSON 응답을 파싱합니다.

    Args:
        base_url (str): API 요청을 보낼 서버 기준 주소입니다.
        path (str): 호출할 API 경로입니다.

    Returns:
        dict | list: 파싱된 JSON 응답 본문입니다.
    """
    with urlopen(f"{base_url}{path}", timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def post_json(base_url: str, path: str, payload: dict) -> dict:
    """스모크 검증 대상 API에 JSON 요청 본문을 POST하고 JSON 응답을 파싱합니다.

    Args:
        base_url (str): API 요청을 보낼 서버 기준 주소입니다.
        path (str): 호출할 API 경로입니다.
        payload (dict): 요청 본문으로 보낼 JSON 직렬화 가능 데이터입니다.

    Returns:
        dict: 파싱된 JSON 응답 본문입니다.
    """
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(2):
        try:
            with urlopen(request, timeout=120) as response:
                if response.status != 200:
                    raise RuntimeError(f"{path} returned HTTP {response.status}")
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code != 429 or attempt > 0:
                raise
            retry_after = exc.headers.get("Retry-After")
            try:
                wait_seconds = int(retry_after) if retry_after is not None else 5
            except ValueError:
                wait_seconds = 5
            time.sleep(max(1, wait_seconds))
    raise RuntimeError(f"{path} did not return a response")


def assert_static_asset(base_url: str, path: str) -> None:
    """패키징된 judge 웹 정적 자산이 HTTP 200과 비어 있지 않은 본문으로 제공되는지 확인합니다.

    Args:
        base_url (str): 정적 자산 요청을 보낼 서버 기준 주소입니다.
        path (str): 확인할 정적 자산 경로입니다.
    """
    with urlopen(f"{base_url}{path}", timeout=5) as response:
        body = response.read()
        if response.status != 200 or not body:
            raise RuntimeError(f"{path} did not return a non-empty HTTP 200 response")
    print(f"verified {path} ({len(body)} bytes)")


def create_smoke_problem(source_root: Path, repo_root: Path, problem_id: str = "06") -> Path:
    """패키지 스모크가 의존할 최소 judge 문제 소스를 임시 작업공간에 생성합니다."""
    problem_root = source_root / "problems" / problem_id
    shutil.copy2(repo_root / "testlib.h", source_root / "testlib.h")
    files = {
        "generator/generator.cpp": GENERATOR_CPP,
        "generator/cases.yml": CASES_YML,
        "validator/validator.cpp": VALIDATOR_CPP,
        "checker/judge.cpp": CHECKER_CPP,
        "solutions/main_solution.ac.cpp": SOLUTION_CPP,
    }
    for relative, content in files.items():
        path = problem_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    metadata = {
        "schemaVersion": 1,
        "problemId": problem_id,
        "title": "Packaged Web Smoke",
        "version": 1,
        "tools": {
            "generator": "generator/generator.cpp",
            "generatorConfig": "generator/cases.yml",
            "validator": "validator/validator.cpp",
            "checker": "checker/judge.cpp",
            "solution": "solutions/main_solution.ac.cpp",
        },
        "defaultProfile": "hidden",
        "limits": {
            "compileTimeoutMs": SMOKE_COMPILE_TIMEOUT_MS,
            "generationTimeoutMs": 5000,
            "solutionTimeoutMs": 2000,
            "userTimeoutMs": 2000,
            "userMemoryLimitMb": 2048,
        },
    }
    (problem_root / "problem.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return problem_root


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
    """wheel 빌드, 패키지 생성, 새 가상환경 설치, 웹 서버 실행, API 실행 검증까지 judge 패키지의 사용자 경로를 순서대로 확인합니다.

    Args:
        repo_root (Path): 빌드와 패키지 생성 명령을 실행할 저장소 루트입니다.
        timeout_seconds (float): 웹 서버 준비를 기다릴 최대 초 단위 시간입니다.
    """
    uv = shutil.which(os.environ.get("UV", "uv"))
    if not uv:
        raise RuntimeError("uv executable was not found")

    with tempfile.TemporaryDirectory(prefix="alj-judge-web-package-smoke-") as tmp_name:
        tmp_root = Path(tmp_name)
        dist_dir = tmp_root / "dist"
        pack_dir = tmp_root / "packs-out"
        venv_dir = tmp_root / "venv"
        runtime = tmp_root / "runtime"
        source_root = tmp_root / "source-project"
        empty_project = tmp_root / "empty-project"
        workspace = tmp_root / "web-workspace"
        for directory in (pack_dir, runtime, source_root, empty_project, workspace):
            directory.mkdir()

        run_command([uv, "build", "--out-dir", str(dist_dir)], cwd=repo_root)
        wheels = sorted(dist_dir.glob("*.whl"))
        if not wheels:
            raise RuntimeError("uv build did not produce a wheel")

        source_problem = create_smoke_problem(source_root, repo_root)
        build_env = {
            **os.environ,
            "ALJ_CACHE_HOME": str(tmp_root / "build-cache"),
            "ALJ_DATA_HOME": str(tmp_root / "build-data"),
            "ALJ_PROJECT_ROOT": str(source_root),
            "ALJ_PYTHON": sys.executable,
        }
        run_command(
            [
                sys.executable,
                "-m",
                "judge",
                "pack",
                "build",
                str(source_problem),
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
    """명령줄 인자를 읽어 judge 웹 패키지 스모크 검증을 실행하고 실패 시 오류를 표준 오류에 출력합니다.

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
        print(f"judge Web package smoke failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
