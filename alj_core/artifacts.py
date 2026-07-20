"""산출물 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

import difflib
from pathlib import Path

from alj_core.errors import JudgeError
from alj_core.paths import cache_root, rel, repo_root, validate_safe_id
from alj_core.utils.text import preview


def wrong_artifact_paths(run_id: str, case_id: str, root: Path | None = None) -> dict[str, Path]:
    validate_safe_id("run id", run_id)
    validate_safe_id("case id", case_id)
    wrong_dir = cache_root(root) / "runs" / run_id / "wrong"
    return {
        "input": wrong_dir / f"{case_id}.in",
        "expected": wrong_dir / f"{case_id}.expected",
        "actual": wrong_dir / f"{case_id}.actual",
    }


def wrong_artifacts(run_id: str, case_id: str, root: Path | None = None) -> dict[str, str]:
    """오답 산출물 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        run_id (str): 저장된 실행 결과와 산출물 디렉터리를 찾는 실행 ID입니다.
        case_id (str): 입력, 출력, 오답 산출물을 구분하는 케이스 ID입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.

    Returns:
        dict[str, str]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 오답 산출물 데이터입니다.
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
    """오답 차이 비교 텍스트 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        run_id (str): 저장된 실행 결과와 산출물 디렉터리를 찾는 실행 ID입니다.
        case_id (str): 입력, 출력, 오답 산출물을 구분하는 케이스 ID입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 오답 차이 비교 텍스트 문자열입니다.
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
    print(wrong_diff_text(run_id, case_id, root), end="")
