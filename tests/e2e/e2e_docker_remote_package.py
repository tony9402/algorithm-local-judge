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
    pypy_summary = summary.get("pypy") or {}
    if pypy_summary:
        lines.append(
            "pypy: "
            f"{pypy_summary.get('status')} · "
            f"{pypy_summary.get('problemId') or '-'} · "
            f"{pypy_summary.get('source') or pypy_summary.get('reason') or '-'}"
        )
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
    return (
        textwrap.dedent(
            f"""
        from __future__ import annotations

        import json
        import os
        import subprocess
        import sys
        import threading
        from pathlib import Path

        from judge.core.paths import cache_root

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


        def synthetic_failure(
            problem_id: str,
            stage: str,
            command: list[str],
            stderr: str,
            stdout: str = "",
        ) -> dict[str, object]:
            return {{
                "problemId": problem_id,
                "stage": stage,
                "command": " ".join(command),
                "exitCode": 1,
                "stdout": trim(stdout),
                "stderr": trim(stderr),
            }}


        def doctor_tools(doctor: subprocess.CompletedProcess[str]) -> dict[str, object]:
            try:
                payload = json.loads(doctor.stdout)
            except json.JSONDecodeError:
                return {{}}
            tools = payload.get("tools")
            return tools if isinstance(tools, dict) else {{}}


        def pypy_runtime_failure(
            tools: dict[str, object],
            doctor: subprocess.CompletedProcess[str],
        ) -> dict[str, object] | None:
            runtime = tools.get("pypyRuntime")
            if isinstance(runtime, dict) and runtime.get("status") == "ok":
                return None
            reason = "PyPy runtime is not available in the Docker image."
            if isinstance(runtime, dict):
                reason = str(runtime.get("hint") or runtime.get("message") or reason)
            return synthetic_failure(
                "__setup__",
                "pypy runtime",
                list(doctor.args),
                reason,
                doctor.stdout,
            )


        def write_file(path: Path, content: str) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


        def create_pypy_smoke_package() -> tuple[str, Path, Path]:
            problem_id = f"pypy-smoke-{{os.getpid()}}"
            package_root = Path("/tmp") / problem_id
            problem_root = package_root / "problems" / problem_id
            user_source = package_root / "submission.py"
            write_file(package_root / "testlib.h", "// docker pypy smoke fixture\\n")
            write_file(
                problem_root / "problem.json",
                json.dumps(
                    {{
                        "schemaVersion": 1,
                        "problemId": problem_id,
                        "title": "Docker PyPy Smoke",
                        "version": 1,
                        "defaultProfile": "sample",
                        "tools": {{
                            "generator": "generator/generator.cpp",
                            "generatorConfig": "generator/cases.yml",
                            "validator": "validator/validator.cpp",
                            "checker": "checker/checker.cpp",
                            "solution": "solutions/reference.cpp",
                        }},
                        "limits": {{
                            "compileTimeoutMs": 5000,
                            "generationTimeoutMs": 5000,
                            "solutionTimeoutMs": 2000,
                            "userTimeoutMs": 2000,
                            "userMemoryLimitMb": 512,
                        }},
                    }},
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            write_file(
                problem_root / "generator" / "cases.yml",
                (
                    "profiles:\\n"
                    "  sample:\\n"
                    "    cases:\\n"
                    "      - name: pypy-smoke\\n"
                    "        type: fixed\\n"
                    "        content: |\\n"
                    "          11 31\\n"
                ),
            )
            write_file(problem_root / "generator" / "generator.cpp", "int main() {{ return 0; }}\\n")
            write_file(problem_root / "validator" / "validator.cpp", "int main() {{ return 0; }}\\n")
            write_file(
                problem_root / "checker" / "checker.cpp",
                (
                    "#include <fstream>\\n"
                    "#include <sstream>\\n"
                    "#include <string>\\n"
                    "int main(int argc, char** argv) {{\\n"
                    "  if (argc < 4) return 1;\\n"
                    "  std::ifstream output(argv[2]);\\n"
                    "  std::ifstream answer(argv[3]);\\n"
                    "  std::ostringstream output_text;\\n"
                    "  std::ostringstream answer_text;\\n"
                    "  output_text << output.rdbuf();\\n"
                    "  answer_text << answer.rdbuf();\\n"
                    "  return output_text.str() == answer_text.str() ? 0 : 1;\\n"
                    "}}\\n"
                ),
            )
            write_file(
                problem_root / "solutions" / "reference.cpp",
                (
                    "#include <iostream>\\n"
                    "int main() {{\\n"
                    "  long long a = 0, b = 0;\\n"
                    "  std::cin >> a >> b;\\n"
                    "  std::cout << (a + b) << '\\\\n';\\n"
                    "  return 0;\\n"
                    "}}\\n"
                ),
            )
            write_file(
                user_source,
                (
                    "import sys\\n"
                    "values = [int(part) for part in sys.stdin.read().split()]\\n"
                    "print(sum(values))\\n"
                ),
            )
            return problem_id, package_root, user_source


        def latest_run_result() -> dict[str, object]:
            run_root = cache_root() / "runs"
            if not run_root.exists():
                return {{}}
            result_paths = sorted(
                run_root.glob("*/result.json"),
                key=lambda path: path.stat().st_mtime,
            )
            if not result_paths:
                return {{}}
            try:
                return json.loads(result_paths[-1].read_text(encoding="utf-8"))
            except Exception:
                return {{}}


        def pypy_smoke(
        ) -> tuple[dict[str, object], dict[str, object] | None]:
            problem_id, package_root, source = create_pypy_smoke_package()
            install_command = ["judge", "problem", "install", str(package_root)]
            install_result = run(install_command)
            summary = {{"status": "running", "problemId": problem_id, "source": str(source)}}
            if install_result.returncode != 0:
                summary["status"] = "failed"
                return summary, command_failure(
                    problem_id,
                    "pypy smoke install",
                    install_command,
                    install_result,
                )

            generate_command = ["judge", "generate", problem_id, "--profile", "sample", "--force"]
            generate_result = run(generate_command)
            if generate_result.returncode != 0:
                summary["status"] = "failed"
                return summary, command_failure(
                    problem_id,
                    "pypy smoke generate",
                    generate_command,
                    generate_result,
                )

            emit(f"pypy smoke {{problem_id}} {{source.name}}")
            command = [
                "judge",
                "--problem",
                problem_id,
                "--profile",
                "sample",
                "--language",
                "pypy",
                str(source),
            ]
            result = run(command)
            summary["status"] = "running" if result.returncode == 0 else "failed"
            if result.returncode != 0:
                return summary, command_failure(problem_id, "pypy smoke", command, result)

            payload = latest_run_result()
            summary["language"] = payload.get("language")
            summary["resultStatus"] = payload.get("status")
            if payload.get("language") != "pypy" or payload.get("status") != "accepted":
                summary["status"] = "failed"
                return summary, synthetic_failure(
                    problem_id,
                    "pypy result metadata",
                    command,
                    (
                        "expected latest result.json to contain "
                        "language=pypy and status=accepted"
                    ),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                )

            emit(f"python default smoke {{problem_id}} {{source.name}}")
            default_command = [
                "judge",
                "--problem",
                problem_id,
                "--profile",
                "sample",
                str(source),
            ]
            default_result = run(default_command)
            if default_result.returncode != 0:
                summary["status"] = "failed"
                return summary, command_failure(
                    problem_id,
                    "python default smoke",
                    default_command,
                    default_result,
                )

            default_payload = latest_run_result()
            summary["pythonDefaultLanguage"] = default_payload.get("language")
            summary["pythonDefaultStatus"] = default_payload.get("status")
            if (
                default_payload.get("language") != "python"
                or default_payload.get("status") != "accepted"
            ):
                summary["status"] = "failed"
                return summary, synthetic_failure(
                    problem_id,
                    "python default metadata",
                    default_command,
                    (
                        "expected latest result.json to contain "
                        "language=python and status=accepted"
                    ),
                    json.dumps(default_payload, ensure_ascii=False, sort_keys=True),
                )

            summary["status"] = "passed"
            return summary, None


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
                "pypy": {{"status": "not_run", "reason": "doctor failed"}},
            }})
        tools = doctor_tools(doctor)
        pypy_failure = pypy_runtime_failure(tools, doctor)
        if pypy_failure is not None:
            finish({{
                "repository": repository,
                "profile": profile,
                "problemCount": 0,
                "generated": [],
                "failures": [pypy_failure],
                "pypy": {{
                    "status": "failed",
                    "reason": pypy_failure["stderr"],
                }},
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
                "pypy": {{"status": "not_run", "reason": "install failed"}},
            }})

        listing = run(["judge", "list"])
        if listing.returncode != 0:
            finish({{
                "repository": repository,
                "profile": profile,
                "problemCount": 0,
                "generated": [],
                "failures": [command_failure("__setup__", "list", listing.args, listing)],
                "pypy": {{"status": "not_run", "reason": "list failed"}},
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
                "pypy": {{"status": "not_run", "reason": "no installed problems"}},
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

        pypy_summary, pypy_failure = pypy_smoke()
        if pypy_failure is not None:
            failures.append(pypy_failure)

        finish({{
            "repository": repository,
            "profile": profile,
            "problemCount": len(problem_ids),
            "generated": generated,
            "failures": failures,
            "pypy": pypy_summary,
        }})
        """
        ).strip()
        + "\n"
    )


class DockerRemotePackageScriptContractTest(unittest.TestCase):
    """Docker 데몬 없이도 컨테이너 내부 검증 스크립트의 핵심 계약을 확인합니다."""

    def test_dockerfile_installs_pypy_runtime(self) -> None:
        """Docker 이미지가 PyPy 런타임을 배포 계약에 포함하는지 확인합니다."""
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("pypy3", dockerfile)
        self.assertIn("COPY alj_core ./alj_core", dockerfile)

    def test_verification_script_checks_pypy_runtime_and_runs_dynamic_pypy_smoke(self) -> None:
        """Docker 검증 스크립트가 PyPy를 고정 문제 없이 실제 Judge 실행으로 검증하는지 확인합니다."""
        script = docker_verification_script()

        self.assertIn("pypyRuntime", script)
        self.assertIn('"--language",', script)
        self.assertIn('"pypy",', script)
        self.assertIn("python default smoke", script)
        self.assertIn("pythonDefaultLanguage", script)
        self.assertIn("create_pypy_smoke_package()", script)
        self.assertIn("pypy-smoke-{os.getpid()}", script)
        self.assertIn('judge", "problem", "install"', script)
        self.assertIn("latest_run_result()", script)
        self.assertNotIn('"06"', script)
        self.assertNotIn("main_solution.ac.py", script)

    def test_failure_report_includes_pypy_context(self) -> None:
        """Docker 실패 리포트가 PyPy smoke 실패 대상을 함께 표시하는지 확인합니다."""
        report = format_failure_report(
            {
                "repository": "owner/repo",
                "profile": "sample",
                "problemCount": 1,
                "generated": [],
                "pypy": {
                    "status": "failed",
                    "problemId": "dynamic-problem",
                    "source": "/data/problem-sources/repo/problems/dynamic-problem/solutions/ac.ac.py",
                },
                "failures": [
                    {
                        "problemId": "dynamic-problem",
                        "stage": "pypy smoke",
                        "command": "judge --language pypy <dynamic-source>",
                        "exitCode": 1,
                        "stdout": "",
                        "stderr": "failure",
                    }
                ],
            }
        )

        self.assertIn("pypy: failed", report)
        self.assertIn("dynamic-problem", report)
        self.assertIn("pypy smoke", report)


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
        self.assertEqual(
            summary.get("pypy", {}).get("status"), "passed", format_failure_report(summary)
        )
        self.assertEqual(summary.get("pypy", {}).get("language"), "pypy")
        self.assertEqual(summary.get("pypy", {}).get("resultStatus"), "accepted")
        self.assertEqual(summary.get("pypy", {}).get("pythonDefaultLanguage"), "python")
        self.assertEqual(summary.get("pypy", {}).get("pythonDefaultStatus"), "accepted")
        self.assertTrue(summary.get("pypy", {}).get("problemId"))
        self.assertTrue((summary.get("pypy", {}).get("source") or "").endswith(".py"))


if __name__ == "__main__":
    unittest.main()
