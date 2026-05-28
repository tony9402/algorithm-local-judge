from __future__ import annotations

import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from judge.core.checksums import verify_sha256_sidecar
from judge.core.errors import JudgeError
from judge.core.generation import generate
from judge.core.pack import build_pack, install_pack, installed_packs, verify_pack
from judge.core.pack_archive import safe_extract_tar
from judge.core.paths import current_platform_id, executable_suffix

ROOT = Path(__file__).resolve().parents[1]
PROBLEM_SOURCE_ROOT = ROOT / "problems" / "algorithm-package" / "problems"


class ProblemPackTest(unittest.TestCase):
    """Tests for source-free problem pack build, verify, and install flows."""

    def test_build_verify_and_install_problem_pack(self) -> None:
        """A built pack should verify, exclude sources, and install into data home."""
        with tempfile.TemporaryDirectory(prefix="alj-pack-test-") as tmp:
            tmp_path = Path(tmp)
            output_dir = tmp_path / "dist"
            data_home = tmp_path / "data"
            cache_home = tmp_path / "cache"
            empty_project_root = tmp_path / "empty-project"
            empty_project_root.mkdir()
            result = build_pack(
                PROBLEM_SOURCE_ROOT / "06",
                "basic",
                current_platform_id(),
                output_dir,
            )

            self.assertTrue(result.archive_path.exists())
            self.assertTrue(
                result.archive_path.with_name(f"{result.archive_path.name}.sha256").exists()
            )
            verify_sha256_sidecar(result.archive_path)
            self.assertTrue(result.solution_checks)
            self.assertTrue(all(check["passed"] for check in result.solution_checks))
            pack = verify_pack(result.archive_path)
            self.assertEqual(pack["packId"], "basic")
            self.assertEqual(pack["supportedPlatforms"], [current_platform_id()])
            self.assertEqual(pack["problems"], ["06"])

            with tarfile.open(result.archive_path, "r:*") as archive:
                names = archive.getnames()
            self.assertEqual(
                sorted(
                    {
                        Path(name).parts[2]
                        for name in names
                        if len(Path(name).parts) > 2 and Path(name).parts[1] == "problems"
                    }
                ),
                ["06"],
            )
            self.assertFalse(
                [name for name in names if Path(name).suffix.lower() in {".cpp", ".hpp", ".h"}]
            )
            self.assertTrue(
                any(
                    name.endswith(
                        f"compiled-tools/{current_platform_id()}/generator{executable_suffix()}"
                    )
                    for name in names
                )
            )

            env = {
                **os.environ,
                "ALJ_PROJECT_ROOT": str(empty_project_root),
                "ALJ_DATA_HOME": str(data_home),
                "ALJ_CACHE_HOME": str(cache_home),
            }
            with patch.dict(os.environ, env, clear=True):
                target = install_pack(result.archive_path)
                self.assertTrue((target / "pack.json").exists())
                self.assertEqual(installed_packs()[0]["packId"], "basic")
                generated = generate("06", "sample", force=True)
                self.assertTrue((generated / "manifest.json").exists())

    def test_pack_archive_rejects_links_and_special_members(self) -> None:
        """Pack extraction should reject links and special tar member types."""
        unsafe_members = [
            ("symlink", tarfile.SYMTYPE, "target.txt"),
            ("hardlink", tarfile.LNKTYPE, "target.txt"),
            ("character-device", tarfile.CHRTYPE, ""),
        ]
        for label, member_type, linkname in unsafe_members:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory(prefix="alj-pack-unsafe-") as tmp:
                    tmp_path = Path(tmp)
                    archive_path = tmp_path / f"{label}.aljpack"
                    with tarfile.open(archive_path, "w:gz") as archive:
                        root = tarfile.TarInfo("pack")
                        root.type = tarfile.DIRTYPE
                        archive.addfile(root)
                        info = tarfile.TarInfo(f"pack/{label}")
                        info.type = member_type
                        info.linkname = linkname
                        archive.addfile(info)

                    with self.assertRaises(JudgeError) as raised:
                        safe_extract_tar(archive_path, tmp_path / "out")

                    self.assertTrue(
                        "unsafe link in pack archive" in str(raised.exception)
                        or "unsupported member type in pack archive" in str(raised.exception)
                    )

    def test_pack_archive_rejects_parent_traversal(self) -> None:
        """Pack extraction should reject parent traversal paths."""
        with tempfile.TemporaryDirectory(prefix="alj-pack-traversal-") as tmp:
            tmp_path = Path(tmp)
            archive_path = tmp_path / "unsafe.aljpack"
            with tarfile.open(archive_path, "w:gz") as archive:
                info = tarfile.TarInfo("../escaped.txt")
                payload = b"bad"
                info.size = len(payload)
                archive.addfile(info, fileobj=io.BytesIO(payload))

            with self.assertRaises(JudgeError) as raised:
                safe_extract_tar(archive_path, tmp_path / "out")

            self.assertIn("unsafe path in pack archive", str(raised.exception))

    def test_pack_archive_rejects_member_count_and_size_caps(self) -> None:
        """Pack archives should enforce extraction resource caps."""
        with tempfile.TemporaryDirectory(prefix="alj-pack-cap-") as tmp:
            tmp_path = Path(tmp)
            member_archive = tmp_path / "too-many.aljpack"
            with tarfile.open(member_archive, "w:gz") as archive:
                for name in ["pack", "pack/a.txt"]:
                    info = tarfile.TarInfo(name)
                    if name == "pack":
                        info.type = tarfile.DIRTYPE
                        archive.addfile(info)
                    else:
                        payload = b"a"
                        info.size = len(payload)
                        archive.addfile(info, fileobj=io.BytesIO(payload))
            with (
                patch("judge.core.security_limits.MAX_ARCHIVE_MEMBERS", 1),
                self.assertRaisesRegex(JudgeError, "too many members"),
            ):
                safe_extract_tar(member_archive, tmp_path / "out-members")
            self.assertFalse((tmp_path / "out-members").exists())

            size_archive = tmp_path / "too-large.aljpack"
            with tarfile.open(size_archive, "w:gz") as archive:
                info = tarfile.TarInfo("pack/a.txt")
                payload = b"abcd"
                info.size = len(payload)
                archive.addfile(info, fileobj=io.BytesIO(payload))
            with (
                patch("judge.core.security_limits.MAX_ARCHIVE_FILE_BYTES", 3),
                self.assertRaisesRegex(JudgeError, "member exceeds size limit"),
            ):
                safe_extract_tar(size_archive, tmp_path / "out-size")
            self.assertFalse((tmp_path / "out-size").exists())

            total_archive = tmp_path / "too-much-total.aljpack"
            with tarfile.open(total_archive, "w:gz") as archive:
                for name, payload in [("pack/a.txt", b"ab"), ("pack/b.txt", b"cd")]:
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    archive.addfile(info, fileobj=io.BytesIO(payload))
            with (
                patch("judge.core.security_limits.MAX_ARCHIVE_TOTAL_BYTES", 3),
                self.assertRaisesRegex(JudgeError, "extracted size exceeds limit"),
            ):
                safe_extract_tar(total_archive, tmp_path / "out-total")
            self.assertFalse((tmp_path / "out-total").exists())


if __name__ == "__main__":
    unittest.main()
