from __future__ import annotations

import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from judge.core.generation import generate
from judge.core.pack import build_pack, install_pack, installed_packs, verify_pack
from judge.core.paths import current_platform_id, executable_suffix

ROOT = Path(__file__).resolve().parents[1]


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
                ROOT / "problems" / "06",
                "basic",
                current_platform_id(),
                output_dir,
            )

            self.assertTrue(result.archive_path.exists())
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


if __name__ == "__main__":
    unittest.main()
