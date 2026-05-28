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
    ROOT,
    create_runnable_minimal_pack,
    create_source_archive,
    create_source_package,
    create_unsafe_tar,
    create_unsafe_tar_link,
    create_unsafe_zip,
    create_unsafe_zip_symlink,
    isolated_runtime,
    run_dir_from_stdout,
    run_judge_cli,
)

PROBLEM_SOURCE_ROOT = ROOT / "problems" / "algorithm-package" / "problems"


class QuietDirectoryHandler(http.server.SimpleHTTPRequestHandler):
    """Serve test fixtures without noisy request logs."""

    def log_message(self, format: str, *args: object) -> None:
        return


class ReusableThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


@contextlib.contextmanager
def serve_directory(directory: Path) -> Iterator[str]:
    """Serve a local directory over HTTP for direct URL E2E tests."""
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
    """E2E coverage for pack and source install flows."""

    def test_pack_build_verify_install_and_generate_from_installed_pack(self) -> None:
        with isolated_runtime("alj-judge-pack-e2e-") as (_directory, runtime):
            output_dir = runtime / "dist"
            build = run_judge_cli(
                runtime,
                "pack",
                "build",
                str(PROBLEM_SOURCE_ROOT / "06"),
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
        with isolated_runtime("alj-judge-unsafe-pack-e2e-") as (_directory, runtime):
            archive = create_unsafe_tar(runtime / "unsafe.aljpack")

            result = run_judge_cli(runtime, "pack", "install", str(archive))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe path in pack archive", result.stderr)

    def test_pack_install_rejects_tar_links(self) -> None:
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
        with isolated_runtime("alj-judge-unsafe-source-e2e-") as (_directory, runtime):
            archive = create_unsafe_zip(runtime / "unsafe-source.zip")

            result = run_judge_cli(runtime, "problem", "install", str(archive))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe path in source archive", result.stderr)

    def test_source_archive_install_rejects_zip_symlink_via_cli(self) -> None:
        with isolated_runtime("alj-judge-unsafe-source-link-e2e-") as (_directory, runtime):
            archive = create_unsafe_zip_symlink(runtime / "unsafe-source-link.zip")

            result = run_judge_cli(runtime, "problem", "install", str(archive))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe link in source archive", result.stderr)

    def test_direct_pack_url_requires_checksum_and_accepts_verified_sources(self) -> None:
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
