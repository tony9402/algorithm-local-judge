"""문제팩 복사 도메인 로직과 파일시스템 변경 정책을 담당합니다.
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
    """문제 into 문제팩 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        pack_problem_dir (Path): 문제팩 문제 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        platform_id (str): platform ID를 조회하거나 저장 위치를 결정할 때 사용하는 식별자입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.
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
