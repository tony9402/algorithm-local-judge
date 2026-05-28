from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUDGE_COMMAND = [sys.executable, "-m", "judge"]


def judge_env(runtime: Path, *, project_root: Path | None = None) -> dict[str, str]:
    """Return isolated environment values for judge E2E tests."""
    return {
        **os.environ,
        "ALJ_CACHE_HOME": str(runtime / "cache"),
        "ALJ_DATA_HOME": str(runtime / "data"),
        "ALJ_PACK_HOME": str(runtime / "packs"),
        "ALJ_SOURCE_HOME": str(runtime / "sources"),
        "ALJ_PROJECT_ROOT": str(project_root) if project_root is not None else str(ROOT),
        "ALJ_PYTHON": sys.executable,
    }


def run_judge_cli(
    runtime: Path,
    *args: str,
    check: bool = False,
    project_root: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the real judge CLI in an isolated runtime."""
    env = judge_env(runtime, project_root=project_root)
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [*JUDGE_COMMAND, *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        command = " ".join([*JUDGE_COMMAND, *args])
        raise AssertionError(
            f"command failed: {command}\n"
            f"returncode: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def run_dir_from_stdout(runtime: Path, stdout: str) -> Path:
    """Return the run artifact directory mentioned by judge stdout."""
    match = re.search(r"run:\s+(.+)", stdout)
    if not match:
        raise AssertionError(f"run directory not found in stdout:\n{stdout}")
    label = match.group(1).strip()
    path = Path(label)
    if not path.is_absolute():
        path = runtime / "cache" / path
    return path


def assert_cli_failed(test: unittest.TestCase, result: subprocess.CompletedProcess[str]) -> None:
    """Assert a CLI command failed and include command output on success."""
    test.assertNotEqual(
        result.returncode,
        0,
        f"command unexpectedly succeeded\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}",
    )


def write_trivial_python_source(target: Path) -> Path:
    """Write a tiny Python submission suitable for always-accepting minimal packs."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("print('ok')\n", encoding="utf-8")
    return target
