"""Judge와 Problem Studio 통합 standalone 빌드 계약을 검증합니다."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.paths import executable_suffix
from scripts.build_standalone import (
    install_compatibility_launcher,
    nuitka_command,
    platform_executable_suffix,
    validate_build_platform,
    validate_staged_bundle,
)


class StandaloneBundleTest(unittest.TestCase):
    """통합 빌드 명령, 실행기, 필수 자산 누락 방지 계약을 검증합니다."""

    def test_nuitka_command_includes_both_apps_and_static_roots(self) -> None:
        command = nuitka_command(Path("/tmp/nuitka-output"))

        self.assertIn("--include-package=problem_studio", command)
        self.assertIn("--include-data-dir=judge/web/static=web/static", command)
        self.assertIn(
            "--include-data-dir=problem_studio/web/static=studio-web/static",
            command,
        )
        self.assertEqual(command[-1], "alj_launcher/__main__.py")

    def test_compatibility_launcher_copies_the_judge_runtime(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-standalone-launcher-") as tmp:
            bin_dir = Path(tmp)
            judge = bin_dir / f"judge{executable_suffix()}"
            judge.write_bytes(b"standalone-runtime")

            studio = install_compatibility_launcher(bin_dir)

            self.assertEqual(studio.name, f"problem-studio{executable_suffix()}")
            self.assertEqual(studio.read_bytes(), judge.read_bytes())

    def test_windows_x64_bundle_uses_two_exe_launchers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-windows-launcher-") as tmp:
            bin_dir = Path(tmp)
            judge = bin_dir / "judge.exe"
            judge.write_bytes(b"windows-standalone-runtime")

            studio = install_compatibility_launcher(bin_dir, "windows-amd64")

            self.assertEqual(platform_executable_suffix("windows-amd64"), ".exe")
            self.assertEqual(studio.name, "problem-studio.exe")
            self.assertEqual(studio.read_bytes(), judge.read_bytes())

    def test_standalone_platform_contract_fails_fast(self) -> None:
        validate_build_platform("windows-amd64", "windows-amd64")
        with self.assertRaisesRegex(JudgeError, "unsupported standalone platform"):
            validate_build_platform("windows-arm64", "windows-arm64")
        with self.assertRaisesRegex(JudgeError, "cross-platform"):
            validate_build_platform("windows-amd64", "linux-amd64")

    def test_stage_validation_rejects_missing_studio_vendor_asset(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-standalone-stage-") as tmp:
            root = Path(tmp)
            suffix = executable_suffix()
            required = [
                Path("bin") / f"judge{suffix}",
                Path("bin") / f"problem-studio{suffix}",
                Path("bin/web/static/index.html"),
                Path("bin/web/static/app.js"),
                Path("bin/studio-web/static/index.html"),
                Path("bin/studio-web/static/app.js"),
            ]
            for relative in required:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("asset\n", encoding="utf-8")

            with self.assertRaisesRegex(JudgeError, "codemirror.min.js"):
                validate_staged_bundle(root)

            vendor = root / "bin/studio-web/static/vendor/codemirror/codemirror.min.js"
            vendor.parent.mkdir(parents=True, exist_ok=True)
            vendor.write_text("window.CodeMirror = {};\n", encoding="utf-8")
            validate_staged_bundle(root)


if __name__ == "__main__":
    unittest.main()
