"""Docker 이미지로 공식 원격 문제 패키지의 전체 데이터 검증 흐름을 확인합니다."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
import unittest
import uuid
from pathlib import Path

from tests.e2e.helpers import ROOT

RUN_DOCKER_TESTS_ENV = "ALJ_RUN_DOCKER_TESTS"
DOCKER_IMAGE_ENV = "ALJ_DOCKER_TEST_IMAGE"
DOCKER_REPOSITORY_ENV = "ALJ_DOCKER_TEST_REPOSITORY"
DOCKER_PROFILE_ENV = "ALJ_DOCKER_TEST_PROFILE"
DOCKER_TIMEOUT_ENV = "ALJ_DOCKER_TEST_TIMEOUT"

DEFAULT_IMAGE = "algorithm-local-judge:docker-e2e"
DEFAULT_REPOSITORY = "tony9402/algorithm-package"
DEFAULT_PROFILE = "full"
DEFAULT_TIMEOUT_SECONDS = 1800
DOCKER_STACK_LIMIT_BYTES = 2048 * 1024 * 1024
SUMMARY_PREFIX = "DOCKER_E2E_SUMMARY "
PROGRESS_PREFIX = "[docker-e2e]"
MAX_FAILURE_OUTPUT_CHARS = 6000


def docker_tests_enabled() -> bool:
    """Docker 통합 테스트를 명시적으로 요청했는지 확인합니다.

    Returns:
        bool: 환경 변수 값이 `1`, `true`, `yes`, `on` 중 하나이면 True입니다.
    """
    value = os.environ.get(RUN_DOCKER_TESTS_ENV, "")
    return value.lower() in {"1", "true", "yes", "on"}


def docker_timeout_seconds() -> int:
    """Docker 빌드와 원격 문제 검증에 사용할 최대 대기 시간을 계산합니다.

    Returns:
        int: 하위 Docker 명령 하나에 적용할 timeout 초 단위 값입니다.
    """
    raw_value = os.environ.get(DOCKER_TIMEOUT_ENV)
    if not raw_value:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def run_command(
    command: list[str],
    *,
    timeout: int,
    cwd: Path = ROOT,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """외부 명령을 실행하며 stdout/stderr를 실시간 표시와 사후 검사용으로 동시에 보존합니다.

    Args:
        command (list[str]): 실행할 명령과 인자 목록입니다.
        timeout (int): 명령 하나가 실행될 수 있는 최대 초 단위 시간입니다.
        cwd (Path): 명령을 실행할 작업 디렉터리입니다.
        check (bool): 실패 종료 코드를 즉시 AssertionError로 바꿀지 여부입니다.

    Returns:
        subprocess.CompletedProcess[str]: 성공한 명령의 종료 코드와 출력입니다.
    """
    print(f"{PROGRESS_PREFIX} $ {' '.join(command)}", flush=True)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    def consume(pipe, sink, chunks: list[str]) -> None:
        if pipe is None:
            return
        try:
            for line in pipe:
                chunks.append(line)
                sink.write(line)
                sink.flush()
        finally:
            pipe.close()

    threads = [
        threading.Thread(
            target=consume,
            args=(process.stdout, sys.stdout, stdout_chunks),
            daemon=True,
        ),
        threading.Thread(
            target=consume,
            args=(process.stderr, sys.stderr, stderr_chunks),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    timed_out = False
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        returncode = process.wait()

    for thread in threads:
        thread.join(timeout=1)

    result = subprocess.CompletedProcess(
        command,
        returncode,
        "".join(stdout_chunks),
        "".join(stderr_chunks),
    )
    if timed_out:
        raise AssertionError(
            "command timed out\n"
            f"command: {' '.join(command)}\n"
            f"timeout: {timeout}s\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    if check and result.returncode != 0:
        raise AssertionError(
            "command failed\n"
            f"command: {' '.join(command)}\n"
            f"exit: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def tail_text(value: str, limit: int = MAX_FAILURE_OUTPUT_CHARS) -> str:
    """긴 로그에서 실패 분석에 필요한 끝부분을 우선 남깁니다."""
    if len(value) <= limit:
        return value
    return value[-limit:]


def format_failure_report(summary: dict) -> str:
    """컨테이너 내부에서 누적한 문제별 실패 목록을 unittest 실패 메시지로 변환합니다."""
    failures = summary.get("failures") or []
    lines = [
        "docker remote package verification failed",
        f"repository: {summary.get('repository')}",
        f"profile: {summary.get('profile')}",
        f"problemCount: {summary.get('problemCount')}",
        f"generatedCount: {len(summary.get('generated') or [])}",
        f"failureCount: {len(failures)}",
    ]
    for index, failure in enumerate(failures, start=1):
        lines.extend(
            [
                "",
                f"[{index}] problem {failure.get('problemId')} · {failure.get('stage')}",
                f"command: {failure.get('command')}",
                f"exit: {failure.get('exitCode')}",
            ]
        )
        stdout = failure.get("stdout") or ""
        stderr = failure.get("stderr") or ""
        if stdout:
            lines.append("stdout:")
            lines.append(stdout)
        if stderr:
            lines.append("stderr:")
            lines.append(stderr)
    return "\n".join(lines)


def docker_verification_script() -> str:
    """컨테이너 안에서 공식 문제 패키지를 설치하고 전체 데이터를 생성하는 스크립트를 만듭니다.

    Returns:
        str: `python`으로 실행할 컨테이너 내부 검증 스크립트입니다.
    """
    return textwrap.dedent(
        f"""
        from __future__ import annotations

        import json
        import os
        import subprocess
        import sys
        import threading

        SUMMARY_PREFIX = {SUMMARY_PREFIX!r}
        PROGRESS_PREFIX = {PROGRESS_PREFIX!r}
        MAX_FAILURE_OUTPUT_CHARS = {MAX_FAILURE_OUTPUT_CHARS!r}


        def emit(message: str) -> None:
            print(PROGRESS_PREFIX + " " + message, flush=True)


        def trim(value: str) -> str:
            if len(value) <= MAX_FAILURE_OUTPUT_CHARS:
                return value
            return value[-MAX_FAILURE_OUTPUT_CHARS:]


        def run(command: list[str]) -> subprocess.CompletedProcess[str]:
            emit("$ " + " ".join(command))
            process = subprocess.Popen(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1,
            )
            stdout_chunks: list[str] = []
            stderr_chunks: list[str] = []

            def consume(pipe, sink, chunks: list[str]) -> None:
                if pipe is None:
                    return
                try:
                    for line in pipe:
                        chunks.append(line)
                        sink.write(line)
                        sink.flush()
                finally:
                    pipe.close()

            threads = [
                threading.Thread(
                    target=consume,
                    args=(process.stdout, sys.stdout, stdout_chunks),
                    daemon=True,
                ),
                threading.Thread(
                    target=consume,
                    args=(process.stderr, sys.stderr, stderr_chunks),
                    daemon=True,
                ),
            ]
            for thread in threads:
                thread.start()
            returncode = process.wait()
            for thread in threads:
                thread.join(timeout=1)
            return subprocess.CompletedProcess(
                command,
                returncode,
                "".join(stdout_chunks),
                "".join(stderr_chunks),
            )


        def command_failure(
            problem_id: str,
            stage: str,
            command: list[str],
            result: subprocess.CompletedProcess[str],
        ) -> dict[str, object]:
            return {{
                "problemId": problem_id,
                "stage": stage,
                "command": " ".join(command),
                "exitCode": result.returncode,
                "stdout": trim(result.stdout),
                "stderr": trim(result.stderr),
            }}


        def finish(summary: dict[str, object]) -> None:
            print(
                SUMMARY_PREFIX
                + json.dumps(summary, ensure_ascii=False, sort_keys=True),
                flush=True,
            )
            if summary.get("failures"):
                raise SystemExit(1)


        def installed_problem_ids(list_output: str) -> list[str]:
            problem_ids = []
            for line in list_output.splitlines():
                stripped = line.strip()
                if not stripped or stripped == "Problems:":
                    continue
                problem_ids.append(stripped.split(maxsplit=1)[0])
            return problem_ids


        repository = os.environ.get({DOCKER_REPOSITORY_ENV!r}, {DEFAULT_REPOSITORY!r})
        profile = os.environ.get({DOCKER_PROFILE_ENV!r}, {DEFAULT_PROFILE!r})

        emit("doctor check")
        doctor = run(["judge", "doctor", "--json"])
        if doctor.returncode != 0:
            finish({{
                "repository": repository,
                "profile": profile,
                "problemCount": 0,
                "generated": [],
                "failures": [command_failure("__setup__", "doctor", doctor.args, doctor)],
            }})

        emit("installing repository " + repository)
        install = run(["judge", "problem", "install", repository])
        if install.returncode != 0:
            finish({{
                "repository": repository,
                "profile": profile,
                "problemCount": 0,
                "generated": [],
                "failures": [command_failure("__setup__", "install", install.args, install)],
            }})

        listing = run(["judge", "list"])
        if listing.returncode != 0:
            finish({{
                "repository": repository,
                "profile": profile,
                "problemCount": 0,
                "generated": [],
                "failures": [command_failure("__setup__", "list", listing.args, listing)],
            }})

        problem_ids = installed_problem_ids(listing.stdout)
        if not problem_ids:
            finish({{
                "repository": repository,
                "profile": profile,
                "problemCount": 0,
                "generated": [],
                "failures": [
                    {{
                        "problemId": "__setup__",
                        "stage": "list",
                        "command": "judge list",
                        "exitCode": 1,
                        "stdout": trim(listing.stdout),
                        "stderr": "no problems were installed from " + repository,
                    }}
                ],
            }})

        generated = []
        failures = []
        for index, problem_id in enumerate(problem_ids, start=1):
            emit(f"[{{index}}/{{len(problem_ids)}}] {{problem_id}} cases compile")
            compile_command = [
                "judge",
                "cases",
                "compile",
                problem_id,
                "--profile",
                profile,
                "--json",
            ]
            compile_result = run(compile_command)
            if compile_result.returncode != 0:
                failures.append(
                    command_failure(problem_id, "cases compile", compile_command, compile_result)
                )
                emit(f"[{{index}}/{{len(problem_ids)}}] {{problem_id}} FAILED cases compile")
                continue

            emit(f"[{{index}}/{{len(problem_ids)}}] {{problem_id}} generate")
            generate_command = ["judge", "generate", problem_id, "--profile", profile, "--force"]
            generate_result = run(generate_command)
            if generate_result.returncode != 0:
                failures.append(
                    command_failure(problem_id, "generate", generate_command, generate_result)
                )
                emit(f"[{{index}}/{{len(problem_ids)}}] {{problem_id}} FAILED generate")
                continue

            generated.append(problem_id)
            emit(f"[{{index}}/{{len(problem_ids)}}] {{problem_id}} OK")

        finish({{
            "repository": repository,
            "profile": profile,
            "problemCount": len(problem_ids),
            "generated": generated,
            "failures": failures,
        }})
        """
    ).strip() + "\n"


@unittest.skipUnless(
    docker_tests_enabled(),
    f"Docker/network integration test; set {RUN_DOCKER_TESTS_ENV}=1 to run.",
)
class DockerRemotePackageE2ETest(unittest.TestCase):
    """Docker 이미지와 공식 문제 패키지 전체 검증 흐름을 실제 컨테이너에서 확인합니다."""

    def test_docker_image_installs_official_package_and_generates_all_problem_data(self) -> None:
        """Ubuntu Docker 이미지가 공식 저장소의 전체 문제 데이터를 생성하는지 검증합니다."""
        image = os.environ.get(DOCKER_IMAGE_ENV, DEFAULT_IMAGE)
        timeout = docker_timeout_seconds()
        repository = os.environ.get(DOCKER_REPOSITORY_ENV, DEFAULT_REPOSITORY)
        profile = os.environ.get(DOCKER_PROFILE_ENV, DEFAULT_PROFILE)

        run_command(["docker", "build", "-t", image, "."], timeout=timeout)

        volume_name = f"alj-docker-e2e-{uuid.uuid4().hex}"
        try:
            result = run_command(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--ulimit",
                    f"stack={DOCKER_STACK_LIMIT_BYTES}:{DOCKER_STACK_LIMIT_BYTES}",
                    "-e",
                    f"{DOCKER_REPOSITORY_ENV}={repository}",
                    "-e",
                    f"{DOCKER_PROFILE_ENV}={profile}",
                    "-v",
                    f"{volume_name}:/data",
                    image,
                    "python",
                    "-c",
                    docker_verification_script(),
                ],
                timeout=timeout,
                check=False,
            )
        finally:
            subprocess.run(
                ["docker", "volume", "rm", "-f", volume_name],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        summary_lines = [
            line[len(SUMMARY_PREFIX) :]
            for line in result.stdout.splitlines()
            if line.startswith(SUMMARY_PREFIX)
        ]
        self.assertEqual(
            len(summary_lines),
            1,
            "docker verification summary missing or duplicated\n"
            f"exit: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}",
        )
        summary = json.loads(summary_lines[0])
        self.assertEqual(summary["repository"], repository)
        self.assertEqual(summary["profile"], profile)
        self.assertFalse(summary.get("failures"), format_failure_report(summary))
        self.assertGreater(summary["problemCount"], 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(summary["problemCount"], len(summary["generated"]))


if __name__ == "__main__":
    unittest.main()
