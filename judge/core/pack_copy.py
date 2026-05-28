"""pack_copy 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from judge.core.compiler import compile_problem_tools
from judge.core.errors import JudgeError
from judge.core.pack_metadata import sanitize_problem_metadata
from judge.core.paths import executable_suffix
from judge.core.problem import TOOL_NAMES, tool_paths
from judge.utils.fs import write_json


def copy_problem_into_pack(
    problem_id: str,
    pack_problem_dir: Path,
    platform_id: str,
    root: Path | None = None,
) -> None:
    """copy_problem_into_pack 함수를 실행하고 결과를 반환합니다.
    
    Args:
        problem_id (str): 문제 ID입니다.
        pack_problem_dir (Path): `pack_problem_dir` 값입니다.
        platform_id (str): `platform_id` 값입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        None: 처리 결과를 반환합니다.
    """
    problem_dir, _, metadata, paths = tool_paths(problem_id, root)
    tools = compile_problem_tools(problem_id, root)
    suffix = executable_suffix()
    pack_problem_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        pack_problem_dir / "problem.json", sanitize_problem_metadata(metadata, platform_id, suffix)
    )
    config_target = pack_problem_dir / "generator" / "cases.yml"
    config_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(paths["generatorConfig"], config_target)
    tool_target_dir = pack_problem_dir / "compiled-tools" / platform_id
    tool_target_dir.mkdir(parents=True, exist_ok=True)
    for name in TOOL_NAMES:
        target = tool_target_dir / f"{name}{suffix}"
        shutil.copy2(tools[name], target)
        target.chmod(target.stat().st_mode | 0o755)
    if problem_dir == pack_problem_dir:
        raise JudgeError("refusing to pack a problem into itself")
