"""artifacts 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import difflib
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.paths import cache_root, rel, repo_root, validate_safe_id
from judge.utils.text import preview


def wrong_artifact_paths(run_id: str, case_id: str, root: Path | None = None) -> dict[str, Path]:
    """wrong_artifact_paths 함수를 실행하고 결과를 반환합니다.
    
    Args:
        run_id (str): `run_id` 값입니다.
        case_id (str): `case_id` 값입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        dict[str, Path]: 처리 결과를 반환합니다.
    """
    validate_safe_id("run id", run_id)
    validate_safe_id("case id", case_id)
    wrong_dir = cache_root(root) / "runs" / run_id / "wrong"
    return {
        "input": wrong_dir / f"{case_id}.in",
        "expected": wrong_dir / f"{case_id}.expected",
        "actual": wrong_dir / f"{case_id}.actual",
    }


def wrong_artifacts(run_id: str, case_id: str, root: Path | None = None) -> dict[str, str]:
    """wrong_artifacts 함수를 실행하고 결과를 반환합니다.
    
    Args:
        run_id (str): `run_id` 값입니다.
        case_id (str): `case_id` 값입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        dict[str, str]: 처리 결과를 반환합니다.
    """
    display_root = root or repo_root()
    files = wrong_artifact_paths(run_id, case_id, root)
    texts = {}
    for name, path in files.items():
        if not path.exists():
            raise JudgeError(f"{name} not found: {rel(path, display_root)}")
        texts[name] = path.read_text(encoding="utf-8", errors="replace")
    return texts


def wrong_diff_text(run_id: str, case_id: str, root: Path | None = None) -> str:
    """wrong_diff_text 함수를 실행하고 결과를 반환합니다.
    
    Args:
        run_id (str): `run_id` 값입니다.
        case_id (str): `case_id` 값입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        str: 처리 결과를 반환합니다.
    """
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
    """show 함수를 실행하고 결과를 반환합니다.
    
    Args:
        run_id (str): `run_id` 값입니다.
        case_id (str): `case_id` 값입니다.
        part (str | None): `part` 값입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
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
    """diff 함수를 실행하고 결과를 반환합니다.
    
    Args:
        run_id (str): `run_id` 값입니다.
        case_id (str): `case_id` 값입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    print(wrong_diff_text(run_id, case_id, root), end="")
