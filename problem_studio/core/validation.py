"""validation 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from judge.core.cases_compile import compile_problem_cases, format_compile_result
from judge.core.errors import JudgeError
from judge.core.generation import generate
from judge.core.paths import rel
from judge.utils.fs import read_json

CASE_PROGRESS_RE = re.compile(r"Validating generated case .+ \((\d+)/(\d+)\)\.")


def compile_cases(workspace: Path, problem_id: str, profile: str | None = None) -> dict[str, Any]:
    """compile_cases 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        profile (str | None): `profile` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    return compile_problem_cases(problem_id, profile, workspace).to_dict()


def generate_profile_data(
    workspace: Path,
    problem_id: str,
    profile: str,
    force: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """generate_profile_data 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        profile (str): `profile` 값입니다.
        force (bool): `force` 값입니다.
        progress (Callable[[str], None] | None): `progress` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    data_dir = generate(
        problem_id,
        profile,
        force=force,
        root=workspace,
        progress=progress,
    )
    manifest = read_json(data_dir / "manifest.json")
    return {
        "problemId": problem_id,
        "profile": manifest.get("profile"),
        "caseCount": len(manifest.get("cases", [])),
        "path": str(data_dir),
        "label": rel(data_dir, workspace),
    }


def validate_all_data(
    workspace: Path,
    problem_id: str,
    force: bool,
    progress: Callable[[str], None],
    cases_result: Any | None = None,
    *,
    prefix_profile_logs: bool = False,
    include_labels: bool = False,
) -> dict[str, Any]:
    """validate_all_data 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        force (bool): `force` 값입니다.
        progress (Callable[[str], None]): `progress` 값입니다.
        cases_result (Any | None): `cases_result` 값입니다.
        prefix_profile_logs (bool): `prefix_profile_logs` 값입니다.
        include_labels (bool): `include_labels` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    if cases_result is None:
        progress("Compiling cases.yml for every profile.")
        cases_result = compile_problem_cases(problem_id, None, workspace)
        if not cases_result.valid:
            raise JudgeError("cases.yml compile failed\n\n" + format_compile_result(cases_result))

    profiles = cases_result.profiles
    total_cases = sum(len(profile.cases) for profile in profiles)
    completed_cases = 0
    generated_profiles: list[dict[str, Any]] = []

    for profile_index, profile in enumerate(profiles, start=1):
        progress(
            f"Generating and validating profile {profile.name} ({profile_index}/{len(profiles)})."
        )

        completed_before_profile = completed_cases

        def profile_progress(
            message: str,
            *,
            profile_name: str = profile.name,
            completed_before: int = completed_before_profile,
        ) -> None:
        """profile_progress 함수를 실행하고 결과를 반환합니다.
        
        Args:
            message (str): 메시지입니다.
            profile_name (str): `profile_name` 값입니다.
            completed_before (int): `completed_before` 값입니다.
        
        Returns:
            None: 처리 결과를 반환합니다.
        """
            if not prefix_profile_logs:
                progress(message)
                return
            prefix = f"{profile_name}: "
            match = CASE_PROGRESS_RE.match(message)
            if match:
                profile_case_index = int(match.group(1))
                progress(
                    f"{prefix}{completed_before + profile_case_index}/{total_cases} "
                    "data generated and validated."
                )
            progress(prefix + message)

        data_dir = generate(
            problem_id,
            profile.name,
            force=force,
            root=workspace,
            progress=profile_progress,
        )
        manifest = read_json(data_dir / "manifest.json")
        case_count = len(manifest.get("cases", []))
        completed_cases += case_count
        progress(
            f"Profile {profile.name} complete: {completed_cases}/{total_cases} "
            "data generated and validated."
        )
        profile_summary = {"name": profile.name, "caseCount": case_count}
        if include_labels:
            profile_summary["label"] = rel(data_dir, workspace)
        generated_profiles.append(profile_summary)

    return {
        "problemId": problem_id,
        "force": force,
        "profileCount": len(generated_profiles),
        "caseCount": completed_cases,
        "profiles": generated_profiles,
    }


def sample_cases(workspace: Path, problem_id: str, force: bool = False) -> dict[str, Any]:
    """sample_cases 함수를 실행하고 결과를 반환합니다.
    
    Args:
        workspace (Path): 작업 공간 객체입니다.
        problem_id (str): 문제 ID입니다.
        force (bool): `force` 값입니다.
    
    Returns:
        dict[str, Any]: 처리 결과를 반환합니다.
    """
    data_dir = generate(problem_id, "sample", force=force, root=workspace)
    manifest = read_json(data_dir / "manifest.json")
    cases = []
    for case in manifest.get("cases", []):
        cases.append(
            {
                "case": case["id"],
                "name": case.get("name") or case["id"],
                "input": (data_dir / case["input"]).read_text(
                    encoding="utf-8",
                    errors="replace",
                ),
                "expected": (data_dir / case["answer"]).read_text(
                    encoding="utf-8",
                    errors="replace",
                ),
            }
        )
    return {
        "problemId": problem_id,
        "profile": manifest.get("profile", "sample"),
        "caseCount": len(cases),
        "label": rel(data_dir, workspace),
        "cases": cases,
    }
