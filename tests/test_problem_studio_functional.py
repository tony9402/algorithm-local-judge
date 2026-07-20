"""문제 스튜디오의 실제 API 조합이 파일 안전성, 빌드, Git 저장소, 레거시 작업공간 계약을 지키는지 검증하는 기능 테스트 모듈입니다."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from alj_core.errors import JudgeError
from alj_core.submission_compiler import prepare_user_submission
from alj_core.tool_compiler import compile_problem_tool
from problem_studio.core.bulk import build_all_problem_packs, run_problem_full_test
from problem_studio.core.git import commit_changes, dirty_paths, redact_remote_url
from problem_studio.core.templates import create_problem
from problem_studio.web.app import create_app


class ProblemStudioFunctionalTest(unittest.TestCase):
    """문제 스튜디오 기능 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def make_client(self) -> tuple[tempfile.TemporaryDirectory[str], TestClient, Path]:
        """클라이언트 테스트가 후속 API 호출이나 명령 실행에 사용할 임시 리소스를 준비합니다.

        Returns:
            tuple[tempfile.TemporaryDirectory[str], TestClient, Path]: 정리 대상 임시 디렉터리, API 클라이언트, 작업공간 경로입니다.
        """
        directory = tempfile.TemporaryDirectory(prefix="alj-problem-studio-functional-")
        workspace = Path(directory.name)
        return directory, TestClient(create_app(workspace)), workspace

    def sse_events(self, text: str) -> list[tuple[str, dict]]:
        """서버 전송 이벤트 응답 본문을 이벤트 이름과 JSON 페이로드 목록으로 파싱합니다.

        Args:
            text (str): 파일에 기록하거나 브라우저에서 기다릴 텍스트입니다.

        Returns:
            list[tuple[str, dict]]: 이벤트 이름과 JSON 페이로드를 순서대로 담은 목록입니다.
        """
        events = []
        for block in text.strip().split("\n\n"):
            if not block:
                continue
            event = "message"
            data_lines = []
            for line in block.splitlines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                if line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())
            events.append((event, json.loads("\n".join(data_lines))))
        return events

    def poll_job(self, client: TestClient, problem_id: str, job_id: str) -> dict:
        """작업 비동기 작업이 종료될 때까지 API를 반복 조회하고 최종 상태를 반환합니다.

        Args:
            client (TestClient): 테스트 대상 API를 호출하는 FastAPI 테스트 클라이언트입니다.
            problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.
            job_id (str): 조회하거나 구성할 백그라운드 작업 식별자입니다.

        Returns:
            dict: 완료 상태가 된 문제별 백그라운드 작업 상태 응답입니다.
        """
        status = {}
        for _ in range(50):
            response = client.get(f"/api/problems/{problem_id}/packs/jobs/{job_id}")
            self.assertEqual(response.status_code, 200, response.text)
            status = response.json()
            if status["status"] != "running":
                return status
            time.sleep(0.01)
        self.fail("background job did not finish")

    def poll_generic_job(self, client: TestClient, job_id: str) -> dict:
        """공통 작업 비동기 작업이 종료될 때까지 API를 반복 조회하고 최종 상태를 반환합니다.

        Args:
            client (TestClient): 테스트 대상 API를 호출하는 FastAPI 테스트 클라이언트입니다.
            job_id (str): 조회하거나 구성할 백그라운드 작업 식별자입니다.

        Returns:
            dict: 완료 상태가 된 공통 백그라운드 작업 상태 응답입니다.
        """
        status = {}
        for _ in range(50):
            response = client.get(f"/api/jobs/{job_id}")
            self.assertEqual(response.status_code, 200, response.text)
            status = response.json()
            if status["status"] not in {"queued", "running", "cancelling"}:
                return status
            time.sleep(0.01)
        self.fail("background job did not finish")

    def test_problem_tool_compile_reuses_hash_manifest_until_source_changes(self) -> None:
        """도구 컴파일은 동일 해시 입력이면 캐시를 쓰고 소스 변경 시 다시 컴파일해야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-tool-cache-") as tmp:
            workspace = Path(tmp)
            create_problem(workspace, "alpha", "Tool Cache")
            calls = []

            def fake_compile(source, output, include_root, timeout_ms, log_path):
                calls.append(source.name)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("compiled\n", encoding="utf-8")
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text("ok\n", encoding="utf-8")
                return {}

            with (
                patch("alj_core.tool_compiler.compile_cpp", side_effect=fake_compile),
                patch(
                    "alj_core.tool_compiler.compiler_identity",
                    return_value={"path": "/fake/g++", "version": "1"},
                ),
            ):
                first = compile_problem_tool("alpha", "checker", workspace)
                second = compile_problem_tool("alpha", "checker", workspace)
                checker = workspace / "problems" / "alpha" / "checker" / "judge.cpp"
                checker.write_text(
                    checker.read_text(encoding="utf-8") + "\n// changed\n", encoding="utf-8"
                )
                third = compile_problem_tool("alpha", "checker", workspace)

        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(calls, ["judge.cpp", "judge.cpp"])

    def test_problem_tool_compile_cache_misses_when_compiler_identity_changes(self) -> None:
        """도구 컴파일 캐시는 컴파일러 path/version이 바뀌면 같은 소스라도 다시 빌드해야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-tool-cache-compiler-") as tmp:
            workspace = Path(tmp)
            create_problem(workspace, "alpha", "Tool Compiler Cache")
            calls = []
            identities = [
                {"path": "/fake/g++-1", "version": "1"},
                {"path": "/fake/g++-1", "version": "1"},
                {"path": "/fake/g++-2", "version": "2"},
            ]

            def fake_compile(source, output, include_root, timeout_ms, log_path):
                calls.append(source.name)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("compiled\n", encoding="utf-8")
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text("ok\n", encoding="utf-8")
                return {}

            with (
                patch("alj_core.tool_compiler.compile_cpp", side_effect=fake_compile),
                patch(
                    "alj_core.tool_compiler.compiler_identity",
                    side_effect=identities,
                ),
            ):
                first = compile_problem_tool("alpha", "checker", workspace)
                second = compile_problem_tool("alpha", "checker", workspace)
                third = compile_problem_tool("alpha", "checker", workspace)

        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(calls, ["judge.cpp", "judge.cpp"])

    def test_cpp_submission_compile_reuses_hash_manifest_until_source_changes(self) -> None:
        """C++ 솔루션 컴파일은 동일 소스 해시이면 캐시 산출물을 재사용해야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-submission-cache-") as tmp:
            workspace = Path(tmp)
            source = workspace / "solution.cpp"
            source.write_text("int main(){return 0;}\n", encoding="utf-8")
            calls = []

            def fake_compile(source_path, output, include_root, timeout_ms, log_path):
                calls.append(source_path.read_text(encoding="utf-8"))
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("compiled\n", encoding="utf-8")
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text("ok\n", encoding="utf-8")
                return {}

            with (
                patch("alj_core.submission_compiler.compile_cpp", side_effect=fake_compile),
                patch(
                    "alj_core.submission_compiler.compiler_identity",
                    return_value={"path": "/fake/g++", "version": "1"},
                ),
            ):
                first = prepare_user_submission(
                    source, workspace / "runs" / "first", 5000, workspace
                )
                second = prepare_user_submission(
                    source, workspace / "runs" / "second", 5000, workspace
                )
                source.write_text("int main(){return 1;}\n", encoding="utf-8")
                third = prepare_user_submission(
                    source, workspace / "runs" / "third", 5000, workspace
                )

        self.assertEqual(first.command, second.command)
        self.assertNotEqual(second.command, third.command)
        self.assertEqual(len(calls), 2)

    def test_cpp_submission_compile_cache_misses_when_compiler_identity_changes(self) -> None:
        """C++ 솔루션 컴파일 캐시는 컴파일러 path/version 변경을 캐시 key에 포함해야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-submission-cache-compiler-") as tmp:
            workspace = Path(tmp)
            source = workspace / "solution.cpp"
            source.write_text("int main(){return 0;}\n", encoding="utf-8")
            calls = []
            identities = [
                {"path": "/fake/g++-1", "version": "1"},
                {"path": "/fake/g++-1", "version": "1"},
                {"path": "/fake/g++-2", "version": "2"},
            ]

            def fake_compile(source_path, output, include_root, timeout_ms, log_path):
                calls.append(source_path.name)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text("compiled\n", encoding="utf-8")
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text("ok\n", encoding="utf-8")
                return {}

            with (
                patch("alj_core.submission_compiler.compile_cpp", side_effect=fake_compile),
                patch(
                    "alj_core.submission_compiler.compiler_identity",
                    side_effect=identities,
                ),
            ):
                first = prepare_user_submission(
                    source, workspace / "runs" / "first", 5000, workspace
                )
                second = prepare_user_submission(
                    source, workspace / "runs" / "second", 5000, workspace
                )
                third = prepare_user_submission(
                    source, workspace / "runs" / "third", 5000, workspace
                )

        self.assertEqual(first.command, second.command)
        self.assertNotEqual(second.command, third.command)
        self.assertEqual(calls, ["solution.cpp", "solution.cpp"])

    def test_java_submission_cache_recompiles_when_main_class_file_is_missing(self) -> None:
        """Java 솔루션 캐시는 manifest만이 아니라 main class 산출물 존재까지 확인해야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-java-cache-") as tmp:
            workspace = Path(tmp)
            source = workspace / "Main.java"
            source.write_text(
                "public class Main { public static void main(String[] args) {} }\n",
                encoding="utf-8",
            )
            compile_calls = []

            def fake_resolve_tool(env_name, candidates):
                return f"/fake/{env_name.lower()}"

            def fake_run_command(command, timeout_ms, **kwargs):
                compile_calls.append(command)
                classes_dir = Path(command[command.index("-d") + 1])
                classes_dir.mkdir(parents=True, exist_ok=True)
                (classes_dir / "Main.class").write_bytes(b"class")
                log_path = kwargs.get("log_path")
                if log_path:
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    log_path.write_text("ok\n", encoding="utf-8")
                return 0, b"", b""

            with (
                patch("alj_core.submission_compiler.resolve_tool", side_effect=fake_resolve_tool),
                patch(
                    "alj_core.submission_compiler.compiler_identity",
                    return_value={"path": "/fake/javac", "version": "1"},
                ),
                patch("alj_core.submission_compiler.run_command", side_effect=fake_run_command),
            ):
                first = prepare_user_submission(
                    source, workspace / "runs" / "first", 5000, workspace
                )
                second = prepare_user_submission(
                    source, workspace / "runs" / "second", 5000, workspace
                )
                class_file = Path(first.command[2]) / "Main.class"
                class_file.unlink()
                third = prepare_user_submission(
                    source, workspace / "runs" / "third", 5000, workspace
                )

        self.assertEqual(first.command, second.command)
        self.assertEqual(first.command, third.command)
        self.assertEqual(len(compile_calls), 2)

    def git(self, cwd: Path, *args: str) -> str:
        """테스트 저장소 안에서 Git 명령을 실행하고 실패 시 표준 오류를 포함해 즉시 실패시킵니다.

        Args:
            cwd (Path): Git 또는 명령줄 도구를 실행할 작업 디렉터리입니다.
            args (str): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.

        Returns:
            str: Git 명령의 표준 출력에서 앞뒤 공백을 제거한 문자열입니다.
        """
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    def make_bare_remote(self, root: Path) -> Path:
        """빈 원격 원격 테스트가 후속 API 호출이나 명령 실행에 사용할 임시 리소스를 준비합니다.

        Args:
            root (Path): 픽스처나 임시 작업공간을 생성할 기준 디렉터리입니다.

        Returns:
            Path: 테스트가 푸시 대상으로 사용할 빈 원격 Git 저장소 경로입니다.
        """
        remote = root / "remote.git"
        seed = root / "seed"
        self.git(root, "init", "--bare", str(remote))
        self.git(root, "clone", str(remote), str(seed))
        self.git(seed, "checkout", "-b", "main")
        self.git(seed, "config", "user.email", "studio@example.com")
        self.git(seed, "config", "user.name", "Problem Studio")
        (seed / "problems").mkdir()
        (seed / "problems" / ".gitkeep").write_text("", encoding="utf-8")
        self.git(seed, "add", "problems/.gitkeep")
        self.git(seed, "commit", "-m", "initial")
        self.git(seed, "push", "-u", "origin", "main")
        self.git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
        return remote

    def test_problem_authoring_metadata_and_file_safety_contract(self) -> None:
        """문제 문제 작성 메타데이터 및 파일 안전성 계약 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)

        created = client.post(
            "/api/problems",
            json={"problem_id": "alpha", "title": "Original", "folder": "Basics"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["metadata"]["limits"]["userMemoryLimitMb"], 2048)

        patched = client.patch(
            "/api/problems/alpha/metadata",
            json={
                "metadata": {
                    "title": "Updated",
                    "folder": "Graphs",
                    "defaultProfile": "sample",
                    "limits": {"userTimeoutMs": 1234},
                }
            },
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["problemId"], "alpha")
        self.assertEqual(patched.json()["title"], "Updated")

        detail = client.get("/api/problems/alpha")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["metadata"]["folder"], "Graphs")
        self.assertEqual(detail.json()["metadata"]["defaultProfile"], "sample")

        metadata_file = json.loads(
            (workspace / "problems" / "alpha" / "problem.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata_file["title"], "Updated")
        self.assertEqual(metadata_file["limits"]["userTimeoutMs"], 1234)

        rejected = client.get("/api/problems/alpha/files/%2E%2E/escaped.txt")
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertIn("invalid problem file path", rejected.json()["detail"])

    def test_problem_metadata_patch_rejects_unsafe_backend_values(self) -> None:
        """문제 메타데이터 수정 거부 안전하지 않은 백엔드 값 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)

        created = client.post(
            "/api/problems",
            json={"problem_id": "alpha", "title": "Original", "folder": "Basics"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        metadata_path = workspace / "problems" / "alpha" / "problem.json"
        before = json.loads(metadata_path.read_text(encoding="utf-8"))

        unsafe_tools = {
            **before["tools"],
            "generator": "../outside.cpp",
        }
        rejected_path = client.patch(
            "/api/problems/alpha/metadata",
            json={"metadata": {"tools": unsafe_tools}},
        )
        self.assertEqual(rejected_path.status_code, 400, rejected_path.text)
        self.assertIn("unsafe generator path", rejected_path.json()["detail"])

        rejected_absolute = client.patch(
            "/api/problems/alpha/metadata",
            json={"metadata": {"tools": {**before["tools"], "checker": "/tmp/checker.cpp"}}},
        )
        self.assertEqual(rejected_absolute.status_code, 400, rejected_absolute.text)
        self.assertIn("unsafe checker path", rejected_absolute.json()["detail"])

        rejected_timeout = client.patch(
            "/api/problems/alpha/metadata",
            json={"metadata": {"limits": {"userTimeoutMs": 0}}},
        )
        self.assertEqual(rejected_timeout.status_code, 400, rejected_timeout.text)
        self.assertIn(
            "userTimeoutMs must be a positive integer",
            rejected_timeout.json()["detail"],
        )

        rejected_memory = client.patch(
            "/api/problems/alpha/metadata",
            json={"metadata": {"limits": {"userMemoryLimitMb": 0}}},
        )
        self.assertEqual(rejected_memory.status_code, 400, rejected_memory.text)
        self.assertIn(
            "userMemoryLimitMb must be a positive integer",
            rejected_memory.json()["detail"],
        )

        after = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(after, before)

    def test_problem_id_can_be_renamed_without_losing_files(self) -> None:
        """문제 식별자 가능 이름 변경 없이 손실 파일 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post(
            "/api/problems",
            json={"problem_id": "alpha", "title": "Renamable", "folder": "Basics"},
        )
        client.put(
            "/api/problems/alpha/files/notes.md",
            json={"content": "keep me\n"},
        )

        renamed = client.patch("/api/problems/alpha/id", json={"problem_id": "beta"})

        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["previousProblemId"], "alpha")
        self.assertEqual(renamed.json()["problemId"], "beta")
        self.assertFalse((workspace / "problems" / "alpha").exists())
        self.assertTrue((workspace / "problems" / "beta" / "notes.md").exists())
        metadata = json.loads(
            (workspace / "problems" / "beta" / "problem.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata["problemId"], "beta")
        self.assertEqual(metadata["title"], "Renamable")
        self.assertEqual(renamed.json()["workspace"]["problemIds"], ["beta"])

        old_detail = client.get("/api/problems/alpha")
        self.assertEqual(old_detail.status_code, 400, old_detail.text)
        new_note = client.get("/api/problems/beta/files/notes.md")
        self.assertEqual(new_note.status_code, 200, new_note.text)
        self.assertEqual(new_note.json()["content"], "keep me\n")

    def test_problem_id_rename_rejects_conflicts_and_unsafe_ids(self) -> None:
        """문제 식별자 이름 변경 거부 충돌 및 안전하지 않은 식별자 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, _workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Alpha"})
        client.post("/api/problems", json={"problem_id": "beta", "title": "Beta"})

        duplicate = client.patch("/api/problems/alpha/id", json={"problem_id": "beta"})
        self.assertEqual(duplicate.status_code, 400, duplicate.text)
        self.assertIn("problem already exists", duplicate.json()["detail"])

        unsafe = client.patch("/api/problems/alpha/id", json={"problem_id": "../escaped"})
        self.assertEqual(unsafe.status_code, 400, unsafe.text)
        self.assertIn("invalid problem id", unsafe.json()["detail"])

    def test_static_index_fragments_are_expanded(self) -> None:
        """정적 색인 조각 확장 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, _workspace = self.make_client()
        self.addCleanup(directory.cleanup)

        response = client.get("/")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertNotIn("<!-- include:", response.text)
        for selector in [
            "studioSidebar",
            "globalTaskStatus",
            "metadataForm",
            "fileEditor",
            "loadingOverlay",
            "newProblemModal",
            "solutionCreateModal",
            "solutionCasesModal",
            "workspaceBuildModal",
            "/static/app.js?v=",
        ]:
            self.assertIn(selector, response.text)

    def test_generate_stream_reports_compile_error_event(self) -> None:
        """생성 스트림 보고 컴파일 오류 이벤트 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, _workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Broken Cases"})
        client.put(
            "/api/problems/alpha/files/generator/cases.yml",
            json={"content": "profiles:\n  hidden:\n    cases: not-a-list\n"},
        )

        response = client.post(
            "/api/problems/alpha/generate/stream",
            json={"profile": "hidden", "force": True},
        )

        self.assertEqual(response.status_code, 200, response.text)
        events = self.sse_events(response.text)
        self.assertEqual(events[-1][0], "error")
        self.assertIn("cases.yml compile failed", events[-1][1]["message"])
        self.assertFalse(any(event == "result" for event, _ in events))

    def test_tools_and_solution_validation_contracts(self) -> None:
        """도구 및 솔루션 검증 계약 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Tools"})
        compiled_path = workspace / ".judge-cache" / "tools" / "generator"

        with patch(
            "problem_studio.web.routes.tools.compile_problem_tool",
            return_value=compiled_path,
        ) as mocked_compile:
            response = client.post(
                "/api/problems/alpha/tools/compile",
                json={"tool": "generator"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["tools"]["generator"], str(compiled_path))
        self.assertEqual(mocked_compile.call_args.args[:2], ("alpha", "generator"))

        invalid_upload = client.post(
            "/api/problems/alpha/solutions/upload",
            files=[("files", ("notes.txt", b"not source\n", "text/plain"))],
        )
        self.assertEqual(invalid_upload.status_code, 400, invalid_upload.text)
        self.assertIn("unsupported solution extension", invalid_upload.json()["detail"])

        invalid_create = client.post(
            "/api/problems/alpha/solutions/create",
            json={"name": "bad token", "expected": "oops", "language": "cpp"},
        )
        self.assertEqual(invalid_create.status_code, 400, invalid_create.text)
        self.assertIn("unknown expected result token", invalid_create.json()["detail"])

    def test_solution_wrong_artifact_preview_contract(self) -> None:
        """솔루션 오답 산출물 미리보기 계약 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, _workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Artifacts"})

        with (
            patch(
                "problem_studio.web.routes.solutions.wrong_artifacts",
                return_value={"input": "1\n", "expected": "2\n", "actual": "3\n"},
            ) as mocked_artifacts,
            patch(
                "problem_studio.web.routes.solutions.wrong_diff_text",
                return_value="-2\n+3\n",
            ) as mocked_diff,
        ):
            response = client.get("/api/problems/alpha/solutions/runs/run-1/wrong/001")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["problemId"], "alpha")
        self.assertEqual(payload["input"], "1\n")
        self.assertEqual(payload["diff"], "-2\n+3\n")
        self.assertFalse(payload["truncation"]["actual"]["truncated"])
        self.assertEqual(mocked_artifacts.call_args.args[0:2], ("run-1", "001"))
        self.assertEqual(mocked_diff.call_args.args[0:2], ("run-1", "001"))

    def test_solution_stress_api_contracts(self) -> None:
        """솔루션 스트레스 API 계약 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, _workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Stress"})

        fake_result = {
            "problemId": "alpha",
            "profile": "hidden",
            "stressRunId": "stress-route",
            "passed": True,
            "iterations": 1,
            "durationSeconds": 300,
            "mismatchCount": 0,
            "mismatches": [],
            "checkedSolutions": [],
        }
        with patch(
            "problem_studio.web.routes.solutions.stress_test_solutions",
            return_value=fake_result,
        ) as mocked_stress:
            started = client.post(
                "/api/problems/alpha/solutions/stress/jobs",
                json={"profile": "hidden", "duration_seconds": 999, "max_cases": 1},
            )
            self.assertEqual(started.status_code, 200, started.text)
            self.assertEqual(started.json()["kind"], "solution-stress")
            self.assertEqual(started.json()["target"]["durationSeconds"], 300)
            finished = self.poll_generic_job(client, started.json()["jobId"])

        self.assertEqual(finished["status"], "succeeded")
        self.assertEqual(finished["result"]["stressRunId"], "stress-route")
        self.assertEqual(mocked_stress.call_args.kwargs["duration_seconds"], 999)

        with patch(
            "problem_studio.web.routes.solutions.stress_mismatch_preview",
            return_value={
                "stressRunId": "stress-route",
                "caseId": "000001",
                "solutionKey": "solution-key",
                "input": "1\n",
                "expected": "1\n",
                "actual": "0\n",
                "diff": "-1\n+0\n",
                "truncation": {},
            },
        ) as mocked_preview:
            preview = client.get(
                "/api/problems/alpha/solutions/stress/runs/stress-route/"
                "mismatches/000001/solution-key"
            )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["problemId"], "alpha")
        self.assertEqual(
            mocked_preview.call_args.args[1:4],
            ("stress-route", "000001", "solution-key"),
        )

        with patch(
            "problem_studio.web.routes.solutions.append_stress_case",
            return_value={
                "problemId": "alpha",
                "profile": "hidden",
                "caseName": "stress-added",
                "mode": "generator",
                "path": "problems/alpha/generator/cases.yml",
                "compile": {"valid": True},
            },
        ) as mocked_append:
            appended = client.post(
                "/api/problems/alpha/solutions/stress/runs/stress-route/"
                "mismatches/000001/solution-key/append",
                json={"profile": "hidden", "mode": "generator", "name": "stress-added"},
            )
        self.assertEqual(appended.status_code, 200, appended.text)
        self.assertEqual(appended.json()["caseName"], "stress-added")
        self.assertEqual(mocked_append.call_args.kwargs["mode"], "generator")

    def test_background_pack_job_failure_and_download_safety(self) -> None:
        """백그라운드 패키지 작업 실패 및 다운로드 안전성 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        client.post("/api/problems", json={"problem_id": "alpha", "title": "Pack"})

        with patch(
            "problem_studio.web.routes.packs.build_problem_pack",
            side_effect=JudgeError("pack failed"),
        ):
            started = client.post(
                "/api/problems/alpha/packs/build",
                json={"pack_id": "basic", "verify_profile": "hidden"},
            )
        self.assertEqual(started.status_code, 200, started.text)
        failed = self.poll_job(client, "alpha", started.json()["jobId"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"], "pack failed")

        outside = workspace.parent / "outside.aljpack"
        outside.write_bytes(b"outside")
        self.addCleanup(lambda: outside.exists() and outside.unlink())
        fake_result = {
            "archivePath": str(outside),
            "archiveLabel": "outside.aljpack",
            "packId": "basic",
            "platformId": "test",
            "problems": ["alpha"],
            "solutionChecks": [],
        }
        with patch(
            "problem_studio.web.routes.packs.build_problem_pack",
            return_value=fake_result,
        ):
            started = client.post(
                "/api/problems/alpha/packs/build",
                json={"pack_id": "basic", "verify_profile": "hidden"},
            )
        succeeded = self.poll_job(client, "alpha", started.json()["jobId"])
        self.assertEqual(succeeded["status"], "succeeded")

        download = client.get(f"/api/problems/alpha/packs/jobs/{started.json()['jobId']}/download")
        self.assertEqual(download.status_code, 400, download.text)
        self.assertIn("outside the output directory", download.json()["detail"])

    def test_full_problem_test_passes_parallel_workers_and_cancel_to_solution_verify(self) -> None:
        """전체 테스트 내부 솔루션 검증도 병렬 worker와 취소 체크를 전달해야 합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-full-test-solutions-") as tmp:
            workspace = Path(tmp)
            progress_messages = []
            cancel_checks = []
            verify_kwargs = {}

            class Token:
                cancelled = False

                def check(self) -> None:
                    cancel_checks.append("checked")

            def fake_verify_solutions(*args, **kwargs) -> dict:
                verify_kwargs.update(kwargs)
                kwargs["cancel_check"]()
                return {
                    "problemId": "01",
                    "profile": "hidden",
                    "passed": True,
                    "verifiedCount": 1,
                    "totalCount": 1,
                    "skippedCount": 0,
                    "checks": [{"source": "solutions/main_solution.ac.cpp", "passed": True}],
                }

            with (
                patch(
                    "problem_studio.core.bulk.compile_problem_cases",
                    return_value=SimpleNamespace(
                        valid=True,
                        profiles=[SimpleNamespace(name="hidden")],
                    ),
                ),
                patch(
                    "problem_studio.core.bulk.compile_problem_tools",
                    return_value={"checker": workspace / "checker"},
                ),
                patch(
                    "problem_studio.core.bulk.validate_all_data",
                    return_value={"caseCount": 1},
                ),
                patch(
                    "problem_studio.core.bulk.verify_solutions",
                    side_effect=fake_verify_solutions,
                ),
            ):
                result = run_problem_full_test(
                    workspace,
                    "01",
                    "hidden",
                    False,
                    progress_messages.append,
                    cancel_token=Token(),
                )

        self.assertTrue(result["passed"])
        self.assertEqual(verify_kwargs["max_workers"], 4)
        self.assertIsNotNone(verify_kwargs["cancel_check"])
        self.assertGreaterEqual(len(cancel_checks), 1)
        self.assertIn("Verifying expected solution results.", progress_messages)

    def test_bulk_build_rejects_unknown_ids_and_skips_pack_on_failure(self) -> None:
        """일괄 빌드 거부 알 수 없는 식별자 및 건너뜀 패키지 실패 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-functional-") as tmp:
            workspace = Path(tmp)
            with patch("problem_studio.core.bulk.discover_problem_ids", return_value=["01"]):
                with self.assertRaisesRegex(JudgeError, "unknown problem id"):
                    build_all_problem_packs(
                        workspace,
                        "basic",
                        Path("dist/packs"),
                        problem_ids=["01", "02"],
                    )

            def failed_full_test(*args, **kwargs) -> dict:
                """전체 검증 실패 결과를 만들어 패키지 빌드 차단 흐름을 검증합니다.

                Args:
                    args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
                    kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

                Returns:
                    dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
                """
                return {
                    "problemId": args[1],
                    "passed": False,
                    "summary": "expected mismatch",
                    "solutionVerification": {"checks": [{"passed": False}]},
                }

            with (
                patch("problem_studio.core.bulk.discover_problem_ids", return_value=["01"]),
                patch(
                    "problem_studio.core.bulk.run_problem_full_test",
                    side_effect=failed_full_test,
                ),
                patch("problem_studio.core.bulk.build_problem_pack_bundle") as mocked_pack,
            ):
                result = build_all_problem_packs(
                    workspace,
                    "basic",
                    Path("dist/packs"),
                    problem_ids=["01"],
                )

        self.assertFalse(result["passed"])
        self.assertEqual(result["packCount"], 0)
        self.assertEqual(result["failedCount"], 1)
        failed_problem = result["problems"][0]
        self.assertEqual(failed_problem["failureStage"], "solutions")
        self.assertEqual(failed_problem["failureStageLabel"], "솔루션 기대 결과")
        self.assertIn("expected mismatch", failed_problem["failureDetails"][0]["message"])
        mocked_pack.assert_not_called()

    def test_bulk_build_deduplicates_ids_and_forwards_solution_checks(self) -> None:
        """일괄 빌드 중복 제거 식별자 및 전달 솔루션 검사 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-functional-") as tmp:
            workspace = Path(tmp)

            def passed_full_test(*args, **kwargs) -> dict:
                """전체 검증 성공 결과를 만들어 패키지 빌드 허용 흐름을 검증합니다.

                Args:
                    args (tuple[Any, ...]): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
                    kwargs (dict[str, Any]): 대상 함수나 가짜 실행기에 전달할 추가 키워드 인자입니다.

                Returns:
                    dict: API 응답이나 가짜 실행 결과를 표현하는 구조화된 사전입니다.
                """
                problem_id = args[1]
                return {
                    "problemId": problem_id,
                    "passed": True,
                    "summary": "ok",
                    "solutionVerification": {
                        "checks": [{"problemId": problem_id, "passed": True}]
                    },
                }

            with (
                patch("problem_studio.core.bulk.discover_problem_ids", return_value=["01", "02"]),
                patch(
                    "problem_studio.core.bulk.run_problem_full_test",
                    side_effect=passed_full_test,
                ),
                patch(
                    "problem_studio.core.bulk.build_problem_pack_bundle",
                    return_value={
                        "archiveLabel": "dist/packs/basic.aljpack",
                        "problems": ["01", "02"],
                    },
                ) as mocked_pack,
            ):
                result = build_all_problem_packs(
                    workspace,
                    "basic",
                    Path("dist/packs"),
                    problem_ids=["01", "01", "02"],
                )

        self.assertTrue(result["passed"])
        self.assertEqual(result["problemCount"], 2)
        self.assertEqual([item["problemId"] for item in result["problems"]], ["01", "02"])
        self.assertEqual(mocked_pack.call_args.args[1], ["01", "02"])
        self.assertEqual(
            mocked_pack.call_args.kwargs["solution_checks"],
            [{"problemId": "01", "passed": True}, {"problemId": "02", "passed": True}],
        )

    def test_git_clone_commit_and_push_feature_branch(self) -> None:
        """Git 복제 커밋 및 푸시 기능 브랜치 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-git-") as tmp:
            root = Path(tmp)
            remote = self.make_bare_remote(root)
            initial_workspace = root / "initial"
            clone_workspace = root / "clone"
            client = TestClient(create_app(initial_workspace))

            cloned = client.post(
                "/api/workspace/git/clone",
                json={
                    "url": str(remote),
                    "path": str(clone_workspace),
                },
            )
            self.assertEqual(cloned.status_code, 200, cloned.text)
            self.git(clone_workspace, "config", "user.email", "studio@example.com")
            self.git(clone_workspace, "config", "user.name", "Problem Studio")
            self.git(clone_workspace, "checkout", "-b", "feature/studio")

            created = client.post(
                "/api/problems",
                json={"problem_id": "alpha", "title": "Git Alpha"},
            )
            self.assertEqual(created.status_code, 200, created.text)

            status = client.get("/api/workspace/git/status")
            self.assertEqual(status.status_code, 200, status.text)
            self.assertTrue(status.json()["isRepository"])
            self.assertTrue(status.json()["dirty"])

            committed = client.post(
                "/api/workspace/git/commit",
                json={"message": "Add alpha problem"},
            )
            self.assertEqual(committed.status_code, 200, committed.text)
            self.assertFalse(committed.json()["dirty"])
            self.assertTrue(committed.json()["writeEnabled"])

            pushed = client.post("/api/workspace/git/push")
            self.assertEqual(pushed.status_code, 200, pushed.text)
            self.assertFalse(pushed.json()["protectedBranch"])
            self.assertTrue(pushed.json()["writeEnabled"])
            refs = self.git(remote, "for-each-ref", "--format=%(refname:short)", "refs/heads")
            self.assertIn("feature/studio", refs.splitlines())

    def test_git_dirty_path_preserves_leading_status_space_for_commit(self) -> None:
        """Git 변경 파일 경로 보존 선행 상태 공간 커밋 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-git-") as tmp:
            workspace = Path(tmp)
            problem_file = workspace / "problems" / "02" / "validator" / "validator.cpp"
            problem_file.parent.mkdir(parents=True)
            problem_file.write_text("// initial\n", encoding="utf-8")
            self.git(workspace, "init")
            self.git(workspace, "config", "user.email", "studio@example.com")
            self.git(workspace, "config", "user.name", "Problem Studio")
            self.git(workspace, "add", "problems/02/validator/validator.cpp")
            self.git(workspace, "commit", "-m", "initial")

            problem_file.write_text("// changed\n", encoding="utf-8")

            self.assertEqual(
                dirty_paths(workspace),
                ["problems/02/validator/validator.cpp"],
            )
            committed = commit_changes(workspace, "Update validator")
            self.assertFalse(committed["dirty"])

    def test_git_push_allows_main_branch_and_redacts_remote(self) -> None:
        """Git 푸시 허용 메인 브랜치 및 마스킹 원격 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-git-") as tmp:
            root = Path(tmp)
            remote = self.make_bare_remote(root)
            workspace = root / "clone"
            self.git(root, "clone", str(remote), str(workspace))
            client = TestClient(create_app(workspace))

            pushed = client.post("/api/workspace/git/push")

            self.assertEqual(pushed.status_code, 200, pushed.text)
            self.assertFalse(pushed.json()["protectedBranch"])
            self.assertEqual(
                redact_remote_url("https://token:secret@github.com/owner/repo.git"),
                "https://github.com/owner/repo.git",
            )

    def test_git_write_actions_can_be_disabled_by_server_policy(self) -> None:
        """Git 쓰기 동작 가능 비활성 서버 정책 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-git-") as tmp:
            root = Path(tmp)
            remote = self.make_bare_remote(root)
            workspace = root / "clone"
            self.git(root, "clone", str(remote), str(workspace))
            client = TestClient(
                create_app(workspace, git_write_enabled=False, workspace_write_enabled=True)
            )

            status = client.get("/api/workspace/git/status")
            self.assertEqual(status.status_code, 200, status.text)
            self.assertFalse(status.json()["writeEnabled"])

            fetched = client.post("/api/workspace/git/fetch")
            self.assertEqual(fetched.status_code, 400, fetched.text)
            self.assertIn("network/write actions are disabled", fetched.json()["detail"])

            committed = client.post(
                "/api/workspace/git/commit",
                json={"message": "blocked"},
            )
            self.assertEqual(committed.status_code, 400, committed.text)
            self.assertIn("network/write actions are disabled", committed.json()["detail"])

    def test_git_status_blocks_tool_repository_remote(self) -> None:
        """Git 상태 차단 도구 저장소 원격 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-git-") as tmp:
            root = Path(tmp)
            remote = self.make_bare_remote(root)
            workspace = root / "clone"
            self.git(root, "clone", str(remote), str(workspace))
            self.git(
                workspace,
                "remote",
                "set-url",
                "origin",
                "https://github.com/tony9402/algorithm-local-judge.git",
            )
            self.git(workspace, "checkout", "-b", "feature/wrong-remote")
            client = TestClient(create_app(workspace))

            created = client.post(
                "/api/problems",
                json={"problem_id": "wrongrepo", "title": "Wrong Repo"},
            )
            self.assertEqual(created.status_code, 200, created.text)

            status = client.get("/api/workspace/git/status")
            self.assertEqual(status.status_code, 200, status.text)
            payload = status.json()
            self.assertEqual(payload["expectedProblemRepository"], "tony9402/algorithm-package")
            self.assertEqual(payload["detectedRepository"], "tony9402/algorithm-local-judge")
            self.assertFalse(payload["problemRepositoryRemote"])
            self.assertTrue(payload["toolRepositoryRemote"])
            self.assertIn("문제 파일은", payload["repositoryWarning"]["message"])

            committed = client.post(
                "/api/workspace/git/commit",
                json={"message": "should be blocked"},
            )
            self.assertEqual(committed.status_code, 400, committed.text)
            self.assertIn("Git 동기화 작업을 막았습니다", committed.json()["detail"])

    def test_repository_clone_uses_workspace_problems_repo_name(self) -> None:
        """저장소 복제 사용 작업공간 문제 저장소 이름 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-repos-") as tmp:
            root = Path(tmp)
            remote = self.make_bare_remote(root)
            workspace = root / "studio"
            client = TestClient(create_app(workspace))

            cloned = client.post(
                "/api/repositories/clone",
                json={
                    "url": str(remote),
                    "repo_name": "algorithm-package",
                },
            )

            self.assertEqual(cloned.status_code, 200, cloned.text)
            target = workspace / "problems" / "algorithm-package"
            self.assertTrue((target / ".git").exists())
            payload = cloned.json()
            self.assertEqual(payload["workspace"]["workspace"], str(target.resolve()))
            self.assertEqual(payload["workspace"]["workspaceRoot"], str(workspace.resolve()))
            self.assertEqual(payload["workspace"]["activeRepository"], "algorithm-package")
            self.assertTrue(payload["workspace"]["repositoryMode"])
            self.assertEqual(payload["repository"]["name"], "algorithm-package")
            self.assertTrue(payload["git"]["isRepository"])
            self.assertEqual(payload["git"]["repositoryName"], "algorithm-package")

    def test_repository_select_scopes_problem_list(self) -> None:
        """저장소 선택 범위 제한 문제 목록 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-repos-") as tmp:
            workspace = Path(tmp) / "studio"
            repo_a = workspace / "problems" / "repo-a"
            repo_b = workspace / "problems" / "repo-b"
            create_problem(repo_a, "01", "Repo A")
            create_problem(repo_b, "01", "Repo B")
            self.git(repo_a, "init")
            self.git(repo_b, "init")
            client = TestClient(create_app(workspace))

            selected_a = client.post("/api/repositories/select", json={"repo_name": "repo-a"})
            self.assertEqual(selected_a.status_code, 200, selected_a.text)
            self.assertEqual(selected_a.json()["workspace"]["activeRepository"], "repo-a")
            self.assertEqual(selected_a.json()["workspace"]["problems"][0]["title"], "Repo A")

            selected_b = client.post("/api/repositories/select", json={"repo_name": "repo-b"})
            self.assertEqual(selected_b.status_code, 200, selected_b.text)
            self.assertEqual(selected_b.json()["workspace"]["activeRepository"], "repo-b")
            self.assertEqual(selected_b.json()["workspace"]["problems"][0]["title"], "Repo B")

    def test_repository_register_opens_existing_nested_repository(self) -> None:
        """저장소 등록 열기 기존 중첩 저장소 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-repos-") as tmp:
            workspace = Path(tmp) / "studio"
            repo = workspace / "problems" / "existing.repo"
            create_problem(repo, "alpha", "Existing Repo")
            self.git(repo, "init")
            client = TestClient(create_app(workspace))

            listed = client.get("/api/repositories")
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertEqual(
                [item["name"] for item in listed.json()["repositories"]],
                ["existing.repo"],
            )

            registered = client.post(
                "/api/repositories/register",
                json={"repo_name": "existing.repo"},
            )

            self.assertEqual(registered.status_code, 200, registered.text)
            payload = registered.json()
            self.assertEqual(payload["workspace"]["activeRepository"], "existing.repo")
            self.assertEqual(payload["repository"]["problemCount"], 1)
            self.assertEqual(payload["workspace"]["problems"][0]["title"], "Existing Repo")

    def test_repository_scoped_jobs_do_not_mix_same_problem_id(self) -> None:
        """저장소 범위 지정 작업 않도록 섞임 같은 문제 식별자 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-repos-") as tmp:
            workspace = Path(tmp) / "studio"
            repo_a = workspace / "problems" / "repo-a"
            repo_b = workspace / "problems" / "repo-b"
            create_problem(repo_a, "01", "Repo A")
            create_problem(repo_b, "01", "Repo B")
            self.git(repo_a, "init")
            self.git(repo_b, "init")
            client = TestClient(create_app(workspace))

            selected_a = client.post("/api/repositories/select", json={"repo_name": "repo-a"})
            self.assertEqual(selected_a.status_code, 200, selected_a.text)
            job_a = client.post("/api/problems/01/cases/jobs", json={"profile": None})
            self.assertEqual(job_a.status_code, 200, job_a.text)
            job_a_id = job_a.json()["jobId"]
            self.assertEqual(job_a.json()["target"]["repositoryName"], "repo-a")

            selected_b = client.post("/api/repositories/select", json={"repo_name": "repo-b"})
            self.assertEqual(selected_b.status_code, 200, selected_b.text)
            job_b = client.post("/api/problems/01/cases/jobs", json={"profile": None})
            self.assertEqual(job_b.status_code, 200, job_b.text)
            job_b_id = job_b.json()["jobId"]
            self.assertEqual(job_b.json()["target"]["repositoryName"], "repo-b")
            self.assertNotEqual(job_a.json()["lane"], job_b.json()["lane"])

            repo_b_jobs = client.get("/api/jobs")
            self.assertEqual(repo_b_jobs.status_code, 200, repo_b_jobs.text)
            self.assertEqual([job["jobId"] for job in repo_b_jobs.json()["jobs"]], [job_b_id])
            repo_a_job_from_b = client.get(f"/api/jobs/{job_a_id}")
            self.assertEqual(repo_a_job_from_b.status_code, 404, repo_a_job_from_b.text)
            scoped_repo_a_job_from_b = client.get(
                f"/api/jobs/{job_a_id}",
                params={"repository_scope": job_a.json()["target"]["repositoryScope"]},
            )
            self.assertEqual(
                scoped_repo_a_job_from_b.status_code, 200, scoped_repo_a_job_from_b.text
            )
            self.assertEqual(scoped_repo_a_job_from_b.json()["jobId"], job_a_id)
            wrong_scoped_repo_a_job_from_b = client.get(
                f"/api/jobs/{job_a_id}",
                params={"repository_scope": job_b.json()["target"]["repositoryScope"]},
            )
            self.assertEqual(
                wrong_scoped_repo_a_job_from_b.status_code,
                404,
                wrong_scoped_repo_a_job_from_b.text,
            )

            client.post("/api/repositories/select", json={"repo_name": "repo-a"})
            repo_a_jobs = client.get("/api/jobs")
            self.assertEqual(repo_a_jobs.status_code, 200, repo_a_jobs.text)
            self.assertEqual([job["jobId"] for job in repo_a_jobs.json()["jobs"]], [job_a_id])
            repo_b_job_from_a = client.get(f"/api/jobs/{job_b_id}")
            self.assertEqual(repo_b_job_from_a.status_code, 404, repo_b_job_from_a.text)
            scoped_repo_b_job_from_a = client.get(
                f"/api/jobs/{job_b_id}",
                params={"repository_scope": job_b.json()["target"]["repositoryScope"]},
            )
            self.assertEqual(
                scoped_repo_b_job_from_a.status_code, 200, scoped_repo_b_job_from_a.text
            )
            self.assertEqual(scoped_repo_b_job_from_a.json()["jobId"], job_b_id)

    def test_git_commit_runs_inside_selected_repository(self) -> None:
        """Git 커밋 실행 내부 선택된 저장소 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-repos-") as tmp:
            root = Path(tmp)
            remote = self.make_bare_remote(root)
            workspace = root / "studio"
            client = TestClient(create_app(workspace))
            cloned = client.post(
                "/api/repositories/clone",
                json={"url": str(remote), "repo_name": "repo-scope"},
            )
            self.assertEqual(cloned.status_code, 200, cloned.text)
            repository = workspace / "problems" / "repo-scope"
            self.git(repository, "config", "user.email", "studio@example.com")
            self.git(repository, "config", "user.name", "Problem Studio")
            self.git(repository, "checkout", "-b", "feature/repo-scope")

            created = client.post(
                "/api/problems",
                json={"problem_id": "alpha", "title": "Scoped Alpha"},
            )
            self.assertEqual(created.status_code, 200, created.text)
            committed = client.post(
                "/api/workspace/git/commit",
                json={"message": "Add scoped alpha"},
            )

            self.assertEqual(committed.status_code, 200, committed.text)
            self.assertFalse(committed.json()["dirty"])
            self.assertEqual(committed.json()["repositoryName"], "repo-scope")
            committed_files = self.git(repository, "show", "--name-only", "--format=", "HEAD")
            self.assertIn("problems/alpha/problem.json", committed_files.splitlines())
            self.assertFalse((workspace / ".git").exists())

    def test_repository_name_rejects_unsafe_paths(self) -> None:
        """저장소 이름 거부 안전하지 않은 경로 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with tempfile.TemporaryDirectory(prefix="alj-problem-studio-repos-") as tmp:
            client = TestClient(create_app(Path(tmp) / "studio"))

            for name in ["../x", ".git", "owner/repo/extra", "bad name"]:
                response = client.post("/api/repositories/register", json={"repo_name": name})
                self.assertEqual(response.status_code, 400, name)
                self.assertIn("invalid repository name", response.json()["detail"])

    def test_legacy_flat_workspace_still_works_with_repository_metadata(self) -> None:
        """레거시 평면 작업공간 계속 동작 저장소 메타데이터 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        directory, client, workspace = self.make_client()
        self.addCleanup(directory.cleanup)
        create_problem(workspace, "alpha", "Legacy Alpha")

        response = client.get("/api/workspace")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["problemIds"], ["alpha"])
        self.assertIsNone(payload["activeRepository"])
        self.assertFalse(payload["repositoryMode"])
        self.assertEqual(payload["repositories"], [])


if __name__ == "__main__":
    unittest.main()
