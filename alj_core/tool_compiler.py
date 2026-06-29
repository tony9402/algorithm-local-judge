"""도구 컴파일러 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from alj_core.compiler_common import compile_cpp, compiler_identity
from alj_core.config import COMPILE_FLAGS, PROTOCOL_VERSION
from alj_core.errors import JudgeError
from alj_core.manifest import cached_sha256_file
from alj_core.paths import build_root, repo_root
from alj_core.problem import (
    TOOL_NAMES,
    is_precompiled_problem,
    problem_workspace_root,
    tool_output_path,
    tool_paths,
)
from alj_core.utils.fs import read_json, write_json
from alj_core.utils.hashing import sha256_json

_TOOL_COMPILE_LOCK = threading.Lock()


def _optional_file_hash(path: Path) -> str | None:
    return cached_sha256_file(path) if path.exists() else None


def _tool_manifest_path(output: Path) -> Path:
    return output.with_name(f"{output.name}.manifest.json")


def _tool_compile_key(
    *,
    problem_id: str,
    tool_name: str,
    metadata_path: Path,
    metadata: dict[str, Any],
    paths: dict[str, Path],
    root: Path,
) -> str:
    testlib = root / "testlib.h"
    payload = {
        "protocolVersion": PROTOCOL_VERSION,
        "compileFlags": COMPILE_FLAGS,
        "compiler": compiler_identity("ALJ_CXX", ["g++"]),
        "problemId": problem_id,
        "problemVersion": metadata.get("version"),
        "tool": tool_name,
        "limits": {
            "compileTimeoutMs": metadata.get("limits", {}).get("compileTimeoutMs", 5000),
        },
        "sourceHashes": {
            "problem": cached_sha256_file(metadata_path),
            tool_name: cached_sha256_file(paths[tool_name]),
            "generatorConfig": cached_sha256_file(paths["generatorConfig"]),
            "testlib": _optional_file_hash(testlib),
        },
    }
    return sha256_json(payload)


def _cached_tool_output(output: Path, key: str) -> bool:
    manifest_path = _tool_manifest_path(output)
    if not output.exists() or not manifest_path.exists():
        return False
    try:
        manifest = read_json(manifest_path)
    except (json.JSONDecodeError, OSError):
        return False
    return manifest.get("compileKey") == key


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
    problem_dir, metadata_path, metadata, paths = tool_paths(problem_id, root)
    if is_precompiled_problem(metadata):
        return paths[tool_name]

    root = problem_workspace_root(problem_dir, root)
    limits = metadata.get("limits", {})
    timeout_ms = limits.get("compileTimeoutMs", 5000)
    logs = build_root(root) / "tools" / problem_id / "logs"
    output = tool_output_path(problem_id, tool_name, root)
    key = _tool_compile_key(
        problem_id=problem_id,
        tool_name=tool_name,
        metadata_path=metadata_path,
        metadata=metadata,
        paths=paths,
        root=root or repo_root(),
    )
    with _TOOL_COMPILE_LOCK:
        if _cached_tool_output(output, key):
            if progress is not None:
                progress(f"Using cached {tool_name} tool.")
            return output
        if progress is not None:
            progress(f"Compiling {tool_name} tool.")
        compile_cpp(paths[tool_name], output, root, timeout_ms, logs / f"{tool_name}.log")
        write_json(
            _tool_manifest_path(output),
            {
                "schemaVersion": 1,
                "problemId": problem_id,
                "tool": tool_name,
                "compileKey": key,
            },
        )
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
