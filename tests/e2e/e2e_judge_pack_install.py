"""패키지 빌드, 설치, 삭제, 원격 다운로드 보안 경로를 실제 명령줄 흐름으로 검증하는 종단 간 테스트 모듈입니다."""

from __future__ import annotations

import contextlib
import functools
import hashlib
import http.server
import json
import socketserver
import threading
import unittest
from collections.abc import Iterator
from pathlib import Path

from tests.e2e.helpers import (
    create_runnable_minimal_pack,
    create_source_archive,
    create_source_package,
    create_unsafe_tar,
    create_unsafe_tar_link,
    create_unsafe_zip,
    create_unsafe_zip_symlink,
    e2e_project_root,
    isolated_runtime,
    run_dir_from_stdout,
    run_judge_cli,
)


class QuietDirectoryHandler(http.server.SimpleHTTPRequestHandler):
    """픽스처 HTTP 서버가 요청 로그를 출력하지 않도록 막아 테스트 출력이 안정적으로 유지되게 하는 핸들러입니다."""

    def log_message(self, format: str, *args: object) -> None:
        """테스트 픽스처 HTTP 서버의 요청 로그 출력을 억제해 실패 출력이 핵심 진단만 담도록 합니다.

        Args:
            format (str): HTTP 서버 로그 포맷 문자열입니다.
            args (object): 명령줄 호출이나 보조 함수에 그대로 전달할 추가 위치 인자입니다.
        """
        return


class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    """짧은 시간에 반복 생성되는 픽스처 HTTP 서버가 같은 포트를 재사용할 수 있게 설정한 서버 클래스입니다."""

    allow_reuse_address = True
    daemon_threads = True


@contextlib.contextmanager
def serve_directory(directory: Path) -> Iterator[str]:
    """로컬 디렉터리를 HTTP로 노출해 직접 URL 설치 시나리오가 실제 다운로드 경계를 지나가게 합니다.

    Args:
        directory (Path): 테스트 HTTP 서버가 정적 파일로 노출할 디렉터리입니다.

    Returns:
        Iterator[str]: 호출자가 비교하거나 다음 명령에 전달할 문자열입니다.
    """
    handler = functools.partial(QuietDirectoryHandler, directory=str(directory))
    with ReusableThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            yield f"http://{host}:{port}"
        finally:
            server.shutdown()
            thread.join(timeout=5)


class JudgePackInstallE2ETest(unittest.TestCase):
    """채점기 패키지 설치 종단 간 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def test_pack_build_verify_install_and_generate_from_installed_pack(self) -> None:
        """패키지 빌드 검증 설치 및 생성 설치된 패키지 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-pack-e2e-") as (_directory, runtime):
            output_dir = runtime / "dist"
            problem_root = e2e_project_root(runtime) / "problems" / "06"
            build = run_judge_cli(
                runtime,
                "pack",
                "build",
                str(problem_root),
                "--pack-id",
                "e2e-basic",
                "--out",
                str(output_dir),
                "--verify-profile",
                "sample",
                check=True,
            )
            self.assertIn("Built pack:", build.stdout)
            archives = list(output_dir.glob("e2e-basic-*.aljpack"))
            self.assertEqual(len(archives), 1)
            archive = archives[0]

            verify = run_judge_cli(runtime, "pack", "verify", str(archive), check=True)
            self.assertIn("Verified pack: e2e-basic", verify.stdout)

            install = run_judge_cli(runtime, "pack", "install", str(archive), check=True)
            self.assertIn("Installed pack:", install.stdout)
            pack_list = run_judge_cli(runtime, "pack", "list", check=True)
            self.assertIn("e2e-basic", pack_list.stdout)
            self.assertIn("06", pack_list.stdout)

            empty_project = runtime / "empty-project"
            empty_project.mkdir()
            generated = run_judge_cli(
                runtime,
                "generate",
                "06",
                "--profile",
                "sample",
                "--force",
                check=True,
                project_root=empty_project,
            )
            self.assertIn("Generated data:", generated.stdout)
            self.assertTrue(list((runtime / "cache" / "problems" / "06").glob("*/manifest.json")))

            run = run_judge_cli(
                runtime,
                "--problem",
                "06",
                "--profile",
                "sample",
                "tests/fixtures/accepted.py",
                check=True,
                project_root=empty_project,
            )
            self.assertIn("Accepted", run.stdout)
            run_dir = run_dir_from_stdout(runtime, run.stdout)
            payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "accepted")
            self.assertEqual(payload["problemId"], "06")

    def test_pack_remove_hides_installed_problem_lifecycle(self) -> None:
        """패키지 제거 숨김 설치된 문제 생명주기 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-pack-remove-e2e-") as (_directory, runtime):
            archive = create_runnable_minimal_pack(
                runtime / "remove-pack.aljpack",
                pack_id="e2e-remove",
                problem_id="remove-problem",
            )
            install = run_judge_cli(runtime, "pack", "install", str(archive), check=True)
            self.assertIn("Installed pack:", install.stdout)
            pack_list = run_judge_cli(runtime, "pack", "list", check=True)
            self.assertIn("e2e-remove", pack_list.stdout)
            self.assertIn("remove-problem", pack_list.stdout)

            removed = run_judge_cli(runtime, "pack", "remove", "e2e-remove", check=True)
            self.assertIn("Removed pack:", removed.stdout)
            pack_list_after = run_judge_cli(runtime, "pack", "list", check=True)
            self.assertNotIn("e2e-remove", pack_list_after.stdout)
            self.assertNotIn("remove-problem", pack_list_after.stdout)

            empty_project = runtime / "empty-project"
            empty_project.mkdir()
            generated = run_judge_cli(
                runtime,
                "generate",
                "remove-problem",
                "--profile",
                "hidden",
                project_root=empty_project,
            )
            self.assertNotEqual(generated.returncode, 0)
            self.assertIn("problem metadata not found", generated.stderr.lower())

    def test_pack_install_rejects_unsafe_tar_member(self) -> None:
        """패키지 설치 거부 안전하지 않은 tar 멤버 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-unsafe-pack-e2e-") as (_directory, runtime):
            archive = create_unsafe_tar(runtime / "unsafe.aljpack")

            result = run_judge_cli(runtime, "pack", "install", str(archive))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe path in pack archive", result.stderr)

    def test_pack_install_rejects_tar_links(self) -> None:
        """패키지 설치 거부 tar 링크 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-unsafe-pack-link-e2e-") as (_directory, runtime):
            for label, hardlink in (("symlink", False), ("hardlink", True)):
                with self.subTest(label=label):
                    archive = create_unsafe_tar_link(
                        runtime / f"unsafe-{label}.aljpack",
                        hardlink=hardlink,
                    )

                    result = run_judge_cli(runtime, "pack", "install", str(archive))

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unsafe link in pack archive", result.stderr)

    def test_source_directory_install_exposes_problem_list(self) -> None:
        """소스 디렉터리 설치 노출 문제 목록 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-source-dir-e2e-") as (_directory, runtime):
            source_package = create_source_package(runtime, "alpha")

            install = run_judge_cli(
                runtime,
                "problem",
                "install",
                str(source_package),
                check=True,
            )
            self.assertIn("Installed source package:", install.stdout)
            self.assertIn("Install type: source fallback", install.stdout)
            self.assertIn(".aljpack release assets are preferred", install.stdout)
            self.assertIn("Only install source packages", install.stdout)
            self.assertIn("Problems: 1", install.stdout)

            problem_list = run_judge_cli(runtime, "problem", "list", check=True)
            self.assertIn("alpha", problem_list.stdout)
            self.assertIn("Alpha Source Problem", problem_list.stdout)

    def test_source_archive_install_exposes_problem_list(self) -> None:
        """소스 아카이브 설치 노출 문제 목록 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-source-zip-e2e-") as (_directory, runtime):
            archive = create_source_archive(runtime / "source-package.zip", "beta")

            install = run_judge_cli(
                runtime,
                "problem",
                "install",
                str(archive),
                check=True,
            )
            self.assertIn("Installed source package:", install.stdout)
            self.assertIn("Install type: source fallback", install.stdout)
            self.assertIn("Only install source packages", install.stdout)
            self.assertIn("Problems: 1", install.stdout)

            problem_list = run_judge_cli(runtime, "problem", "list", check=True)
            self.assertIn("beta", problem_list.stdout)
            self.assertIn("Alpha Source Problem", problem_list.stdout)

    def test_source_archive_install_rejects_unsafe_zip_member_via_cli(self) -> None:
        """소스 아카이브 설치 거부 안전하지 않은 zip 멤버 경유 명령줄 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-unsafe-source-e2e-") as (_directory, runtime):
            archive = create_unsafe_zip(runtime / "unsafe-source.zip")

            result = run_judge_cli(runtime, "problem", "install", str(archive))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe path in source archive", result.stderr)

    def test_source_archive_install_rejects_zip_symlink_via_cli(self) -> None:
        """소스 아카이브 설치 거부 zip 심볼릭 링크 경유 명령줄 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-unsafe-source-link-e2e-") as (_directory, runtime):
            archive = create_unsafe_zip_symlink(runtime / "unsafe-source-link.zip")

            result = run_judge_cli(runtime, "problem", "install", str(archive))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe link in source archive", result.stderr)

    def test_direct_pack_url_requires_checksum_and_accepts_verified_sources(self) -> None:
        """직접 패키지 주소 요구 체크섬 및 허용 검증된 소스 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        with isolated_runtime("alj-judge-direct-pack-e2e-") as (_directory, runtime):
            explicit_archive = create_runnable_minimal_pack(
                runtime / "direct-checksum.aljpack",
                pack_id="e2e-direct-checksum",
                problem_id="direct-checksum",
            )
            sidecar_archive = create_runnable_minimal_pack(
                runtime / "direct-sidecar.aljpack",
                pack_id="e2e-direct-sidecar",
                problem_id="direct-sidecar",
            )
            explicit_checksum = hashlib.sha256(explicit_archive.read_bytes()).hexdigest()
            sidecar_checksum = hashlib.sha256(sidecar_archive.read_bytes()).hexdigest()
            sidecar_archive.with_name(f"{sidecar_archive.name}.sha256").write_text(
                f"{sidecar_checksum}  {sidecar_archive.name}\n",
                encoding="utf-8",
            )

            with serve_directory(runtime) as base_url:
                explicit_url = f"{base_url}/{explicit_archive.name}"
                sidecar_url = f"{base_url}/{sidecar_archive.name}"

                missing_checksum = run_judge_cli(runtime, "problem", "install", explicit_url)
                self.assertNotEqual(missing_checksum.returncode, 0)
                self.assertIn("requires --checksum", missing_checksum.stderr)

                explicit_install = run_judge_cli(
                    runtime,
                    "problem",
                    "install",
                    explicit_url,
                    "--checksum",
                    explicit_checksum,
                    check=True,
                )
                self.assertIn("Installed problem pack:", explicit_install.stdout)
                self.assertIn("Checksum: verified (--checksum)", explicit_install.stdout)

                sidecar_install = run_judge_cli(
                    runtime,
                    "problem",
                    "install",
                    sidecar_url,
                    check=True,
                )
                self.assertIn("Installed problem pack:", sidecar_install.stdout)
                self.assertIn("Checksum: verified", sidecar_install.stdout)

            problem_list = run_judge_cli(runtime, "problem", "list", check=True)
            self.assertIn("direct-checksum", problem_list.stdout)
            self.assertIn("direct-sidecar", problem_list.stdout)


if __name__ == "__main__":
    unittest.main()
