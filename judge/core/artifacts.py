from __future__ import annotations

import difflib
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.paths import cache_root, rel, repo_root, validate_safe_id
from judge.utils.text import preview


def wrong_artifact_paths(run_id: str, case_id: str, root: Path | None = None) -> dict[str, Path]:
    """Return saved wrong-answer artifact paths for one run case."""
    validate_safe_id("run id", run_id)
    validate_safe_id("case id", case_id)
    wrong_dir = cache_root(root) / "runs" / run_id / "wrong"
    return {
        "input": wrong_dir / f"{case_id}.in",
        "expected": wrong_dir / f"{case_id}.expected",
        "actual": wrong_dir / f"{case_id}.actual",
    }


def wrong_artifacts(run_id: str, case_id: str, root: Path | None = None) -> dict[str, str]:
    """Return saved wrong-answer artifact text for web/API callers."""
    display_root = root or repo_root()
    files = wrong_artifact_paths(run_id, case_id, root)
    texts = {}
    for name, path in files.items():
        if not path.exists():
            raise JudgeError(f"{name} not found: {rel(path, display_root)}")
        texts[name] = path.read_text(encoding="utf-8", errors="replace")
    return texts


def wrong_diff_text(run_id: str, case_id: str, root: Path | None = None) -> str:
    """Return a unified diff between expected and actual wrong outputs."""
    files = wrong_artifact_paths(run_id, case_id, root)
    expected = files["expected"]
    actual = files["actual"]
    if not expected.exists() or not actual.exists():
        raise JudgeError(f"wrong output files not found for run {run_id}, case {case_id}")
    expected_lines = expected.read_text(encoding="utf-8", errors="replace").splitlines(
        keepends=True
    )
    actual_lines = actual.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    lines = list(
        difflib.unified_diff(expected_lines, actual_lines, fromfile="expected", tofile="actual")
    )
    if not lines:
        return "No differences.\n"
    text = "".join(lines[:400])
    if len(lines) > 400:
        text += "\n... diff truncated ...\n"
    return text


def show(run_id: str, case_id: str, part: str | None = None, root: Path | None = None) -> None:
    """Print saved wrong-answer artifacts for one run case."""
    display_root = root or repo_root()
    files = wrong_artifact_paths(run_id, case_id, root)
    selected = [part] if part else ["input", "expected", "actual"]
    for name in selected:
        path = files[name]
        if not path.exists():
            raise JudgeError(f"{name} not found: {rel(path, display_root)}")
        text = preview(path)
        print(f"== {name}: {rel(path, display_root)} ==")
        print(text, end="" if text.endswith("\n") else "\n")


def diff(run_id: str, case_id: str, root: Path | None = None) -> None:
    """Print a unified diff between expected and actual wrong outputs."""
    print(wrong_diff_text(run_id, case_id, root), end="")
