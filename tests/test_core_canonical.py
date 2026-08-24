"""Canonical ``alj_core``와 legacy ``judge`` import의 호환 계약을 검증합니다."""

from __future__ import annotations

import importlib
import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

MODULE_ALIASES = {
    "judge.core.artifacts": "alj_core.artifacts",
    "judge.core.cases_block_schema": "alj_core.cases_block_schema",
    "judge.core.cases_compile": "alj_core.cases_compile",
    "judge.core.cases_concrete_schema": "alj_core.cases_concrete_schema",
    "judge.core.cases_diagnostics": "alj_core.cases_diagnostics",
    "judge.core.cases_expansion": "alj_core.cases_expansion",
    "judge.core.cases_format": "alj_core.cases_format",
    "judge.core.cases_io": "alj_core.cases_io",
    "judge.core.cases_models": "alj_core.cases_models",
    "judge.core.cases_profile_compile": "alj_core.cases_profile_compile",
    "judge.core.cases_profiles": "alj_core.cases_profiles",
    "judge.core.cases_schema": "alj_core.cases_schema",
    "judge.core.checksums": "alj_core.checksums",
    "judge.core.compiler": "alj_core.compiler",
    "judge.core.compiler_common": "alj_core.compiler_common",
    "judge.core.config": "alj_core.config",
    "judge.core.errors": "alj_core.errors",
    "judge.core.generation": "alj_core.generation",
    "judge.core.languages": "alj_core.languages",
    "judge.core.manifest": "alj_core.manifest",
    "judge.core.pack": "alj_core.pack",
    "judge.core.pack_archive": "alj_core.pack_archive",
    "judge.core.pack_build": "alj_core.pack_build",
    "judge.core.pack_copy": "alj_core.pack_copy",
    "judge.core.pack_install": "alj_core.pack_install",
    "judge.core.pack_metadata": "alj_core.pack_metadata",
    "judge.core.pack_verify": "alj_core.pack_verify",
    "judge.core.paths": "alj_core.paths",
    "judge.core.problem": "alj_core.problem",
    "judge.core.problem_constants": "alj_core.problem_constants",
    "judge.core.problem_discovery": "alj_core.problem_discovery",
    "judge.core.problem_metadata": "alj_core.problem_metadata",
    "judge.core.runner": "alj_core.runner",
    "judge.core.security_limits": "alj_core.security_limits",
    "judge.core.solution_expectations": "alj_core.solution_expectations",
    "judge.core.solution_models": "alj_core.solution_models",
    "judge.core.solution_validation": "alj_core.solution_validation",
    "judge.core.submission": "alj_core.submission",
    "judge.core.submission_cases": "alj_core.submission_cases",
    "judge.core.submission_compiler": "alj_core.submission_compiler",
    "judge.core.submission_paths": "alj_core.submission_paths",
    "judge.core.submission_result": "alj_core.submission_result",
    "judge.core.submission_status": "alj_core.submission_status",
    "judge.core.submission_warmup": "alj_core.submission_warmup",
    "judge.core.tool_compiler": "alj_core.tool_compiler",
    "judge.core.toolchain_manifest": "alj_core.toolchain_manifest",
    "judge.core.toolchains": "alj_core.toolchains",
    "judge.utils.fs": "alj_core.utils.fs",
    "judge.utils.hashing": "alj_core.utils.hashing",
    "judge.utils.process": "alj_core.utils.process",
    "judge.utils.text": "alj_core.utils.text",
}


class CanonicalCoreCompatibilityTest(unittest.TestCase):
    """Legacy import가 canonical 구현과 동일한 객체·동작을 제공하는지 검증합니다."""

    def test_legacy_modules_are_canonical_module_aliases(self) -> None:
        """모든 선택 모듈의 legacy와 canonical import는 같은 모듈 객체여야 합니다."""
        for legacy_name, canonical_name in MODULE_ALIASES.items():
            with self.subTest(legacy=legacy_name):
                legacy = importlib.import_module(legacy_name)
                canonical = importlib.import_module(canonical_name)
                self.assertIs(legacy, canonical)

    def test_every_overlapping_legacy_module_has_an_alias_contract(self) -> None:
        """동명 구현이 다시 조용히 추가되지 않도록 전체 겹침 목록을 계약으로 고정합니다."""
        overlapping = set()
        for legacy_package, canonical_package, legacy_prefix in (
            (ROOT / "judge" / "core", ROOT / "alj_core", "judge.core"),
            (ROOT / "judge" / "utils", ROOT / "alj_core" / "utils", "judge.utils"),
        ):
            canonical_names = {
                path.name for path in canonical_package.glob("*.py") if path.name != "__init__.py"
            }
            overlapping.update(
                f"{legacy_prefix}.{path.stem}"
                for path in legacy_package.glob("*.py")
                if path.name in canonical_names
            )

        self.assertEqual(set(MODULE_ALIASES), overlapping)

    def test_public_types_and_functions_keep_identity(self) -> None:
        """공개 예외·모델·함수는 legacy import에서도 canonical 객체 정체성을 유지해야 합니다."""
        from alj_core.cases_models import CompiledCase as CanonicalCompiledCase
        from alj_core.errors import JudgeError as CanonicalJudgeError
        from alj_core.languages import normalize_language_id as canonical_normalize
        from judge.core.cases_models import CompiledCase as LegacyCompiledCase
        from judge.core.errors import JudgeError as LegacyJudgeError
        from judge.core.languages import normalize_language_id as legacy_normalize

        self.assertIs(LegacyJudgeError, CanonicalJudgeError)
        self.assertIs(LegacyCompiledCase, CanonicalCompiledCase)
        self.assertIs(legacy_normalize, canonical_normalize)

    def test_installed_pack_paths_and_facade_live_in_canonical_core(self) -> None:
        """로컬 설치 기능도 legacy 의존 없이 정본 API에서 제공되어야 합니다."""
        from alj_core.pack import install_pack as canonical_install_pack
        from alj_core.pack_install import install_pack as canonical_install_implementation
        from alj_core.paths import problem_pack_root as canonical_pack_root
        from judge.core.pack import install_pack as legacy_install_pack
        from judge.core.paths import problem_pack_root as legacy_pack_root

        with tempfile.TemporaryDirectory(prefix="alj-core-data-") as temporary:
            data_home = Path(temporary) / "data"
            with patch.dict(os.environ, {"ALJ_DATA_HOME": str(data_home)}, clear=True):
                expected = data_home.resolve() / "problem-packs"
                self.assertEqual(canonical_pack_root(), expected)
                self.assertEqual(legacy_pack_root(), expected)

        self.assertIs(canonical_install_pack, canonical_install_implementation)
        self.assertIs(legacy_install_pack, canonical_install_implementation)

    def test_default_user_paths_follow_the_host_operating_system(self) -> None:
        from alj_core.paths import default_cache_root, user_data_root

        with tempfile.TemporaryDirectory(prefix="alj-platform-paths-") as temporary:
            home = Path(temporary).resolve()
            with (
                patch("alj_core.paths.Path.home", return_value=home),
                patch("alj_core.paths.platform.system", return_value="Darwin"),
                patch.dict(os.environ, {}, clear=True),
            ):
                self.assertEqual(
                    user_data_root(),
                    home / "Library" / "Application Support" / "algorithm-local-judge",
                )
                self.assertEqual(
                    default_cache_root(), home / "Library" / "Caches" / "algorithm-local-judge"
                )

            with (
                patch("alj_core.paths.Path.home", return_value=home),
                patch("alj_core.paths.platform.system", return_value="Linux"),
                patch.dict(os.environ, {}, clear=True),
            ):
                self.assertEqual(
                    user_data_root(), home / ".local" / "share" / "algorithm-local-judge"
                )
                self.assertEqual(
                    default_cache_root(), home / ".cache" / "algorithm-local-judge"
                )

    def test_user_runtime_marker_becomes_the_project_root(self) -> None:
        from alj_core.paths import RUNTIME_MARKER, repo_root

        with tempfile.TemporaryDirectory(prefix="alj-user-runtime-") as temporary:
            runtime = Path(temporary).resolve()
            (runtime / RUNTIME_MARKER).write_text("runtime\n", encoding="utf-8")
            with (
                patch("alj_core.paths.sys.prefix", str(runtime)),
                patch.dict(os.environ, {}, clear=True),
            ):
                self.assertEqual(repo_root(), runtime)

    def test_legacy_security_limit_patch_controls_canonical_archive(self) -> None:
        """Legacy limit monkeypatch는 canonical archive 구현이 참조하는 값도 변경해야 합니다."""
        from alj_core.errors import JudgeError
        from judge.core.pack_archive import safe_tar_members

        with tempfile.TemporaryDirectory(prefix="alj-core-contract-") as temporary:
            archive_path = Path(temporary) / "fixture.tar"
            with tarfile.open(archive_path, "w") as archive:
                for name in ("one.txt", "two.txt"):
                    info = tarfile.TarInfo(name)
                    payload = name.encode()
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))

            with patch("judge.core.security_limits.MAX_ARCHIVE_MEMBERS", 1):
                with self.assertRaises(JudgeError):
                    safe_tar_members(archive_path)

    def test_legacy_pack_metadata_patch_reaches_canonical_function_globals(self) -> None:
        """Legacy dependency patch가 canonical pack metadata 내부에서도 관찰돼야 합니다."""
        from alj_core.pack_metadata import manifest_files as canonical_manifest_files
        from judge.core.pack_metadata import manifest_files as legacy_manifest_files

        with tempfile.TemporaryDirectory(prefix="alj-core-contract-") as temporary:
            pack_dir = Path(temporary)
            (pack_dir / "payload.txt").write_text("payload", encoding="utf-8")
            with patch("judge.core.pack_metadata.sha256_file", return_value="patched-digest"):
                expected = [{"path": "payload.txt", "sha256": "patched-digest"}]
                self.assertEqual(legacy_manifest_files(pack_dir), expected)
                self.assertEqual(canonical_manifest_files(pack_dir), expected)


if __name__ == "__main__":
    unittest.main()
