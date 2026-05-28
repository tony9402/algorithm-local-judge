"""도구 컴파일러 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from judge.core.compiler_common import compile_cpp
from judge.core.errors import JudgeError
from judge.core.paths import build_root
from judge.core.problem import (
    TOOL_NAMES,
    is_precompiled_problem,
    problem_workspace_root,
    tool_output_path,
    tool_paths,
)


def compile_problem_tool(
    problem_id: str,
    tool_name: str,
    root: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """문제 도구 소스와 설정을 실행 가능한 산출물과 진단 정보로 변환합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        tool_name (str): 도구 이름를 사용자 표시와 내부 조회에 함께 사용하는 이름입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.
        progress (Callable[[str], None] | None): 장시간 작업의 단계와 메시지를 UI 작업 상태로 전달하는 콜백입니다.

    Returns:
        Path: 검증된 문제 도구 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    if tool_name not in TOOL_NAMES:
        raise JudgeError(f"unknown problem tool: {tool_name}")
    problem_dir, _, metadata, paths = tool_paths(problem_id, root)
    if is_precompiled_problem(metadata):
        return paths[tool_name]

    root = problem_workspace_root(problem_dir, root)
    limits = metadata.get("limits", {})
    timeout_ms = limits.get("compileTimeoutMs", 5000)
    logs = build_root(root) / "tools" / problem_id / "logs"
    output = tool_output_path(problem_id, tool_name, root)
    if progress is not None:
        progress(f"Compiling {tool_name} tool.")
    compile_cpp(paths[tool_name], output, root, timeout_ms, logs / f"{tool_name}.log")
    return output


def compile_problem_tools(
    problem_id: str,
    root: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Path]:
    """문제 도구 소스와 설정을 실행 가능한 산출물과 진단 정보로 변환합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.
        progress (Callable[[str], None] | None): 장시간 작업의 단계와 메시지를 UI 작업 상태로 전달하는 콜백입니다.

    Returns:
        dict[str, Path]: 검증된 문제 도구 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    _, _, metadata, paths = tool_paths(problem_id, root)
    if is_precompiled_problem(metadata):
        return {name: paths[name] for name in TOOL_NAMES}

    outputs = {}
    total = len(TOOL_NAMES)
    for index, name in enumerate(TOOL_NAMES, start=1):
        if progress is not None:
            progress(f"Compiling {name} tool ({index}/{total}).")
        outputs[name] = compile_problem_tool(problem_id, name, root, progress=None)
    return outputs
