from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from judge.core.pack import build_pack, build_pack_for_problem_ids
from judge.core.paths import current_platform_id, rel
from judge.core.solution_validation import (
    discover_solution_expectations,
    verify_problem_solutions,
)
from problem_studio.core.workspace import problem_dir

SOLUTION_WARMUP_PROFILE = "sample"


def list_solutions(workspace: Path, problem_id: str) -> list[dict[str, Any]]:
    """Return solution files and their expected statuses for one problem."""
    base = problem_dir(workspace, problem_id)
    return [
        {
            "path": rel(expectation.path, base),
            "token": expectation.token,
            "expectedStatus": expectation.status,
        }
        for expectation in discover_solution_expectations(base)
    ]


def verify_solutions(
    workspace: Path,
    problem_id: str,
    profile: str = "hidden",
    progress: Callable[[str], None] | None = None,
    raise_on_failure: bool = True,
    solutions: list[str] | None = None,
) -> dict[str, Any]:
    """Run expected-result solution checks for a problem."""
    return verify_problem_solutions(
        problem_id,
        profile,
        workspace,
        progress=progress,
        raise_on_failure=raise_on_failure,
        solution_paths=solutions,
        warmup_profile=SOLUTION_WARMUP_PROFILE,
    ).to_dict(workspace)


def build_problem_pack(
    workspace: Path,
    problem_id: str,
    pack_id: str,
    output_dir: Path,
    platform_id: str | None = None,
    verify_profile: str = "hidden",
    cancel_token: Any | None = None,
) -> dict[str, Any]:
    """Verify solutions and build one source-free problem pack."""
    if cancel_token:
        cancel_token.check()
    resolved_output_dir = output_dir if output_dir.is_absolute() else workspace / output_dir
    result = build_pack(
        problem_dir(workspace, problem_id),
        pack_id,
        platform_id or current_platform_id(),
        resolved_output_dir,
        verify_profile,
        warmup_profile=SOLUTION_WARMUP_PROFILE,
    )
    if cancel_token:
        cancel_token.check()
    return {
        "archivePath": str(result.archive_path),
        "archiveLabel": rel(result.archive_path, workspace),
        "packId": result.pack_id,
        "platformId": result.platform_id,
        "problems": result.problems,
        "solutionChecks": result.solution_checks,
    }


def build_problem_pack_bundle(
    workspace: Path,
    problem_ids: list[str],
    pack_id: str,
    output_dir: Path,
    platform_id: str | None = None,
    verify_profile: str = "hidden",
    solution_checks: list[dict[str, object]] | None = None,
) -> dict[str, Any]:
    """Build one source-free problem pack containing multiple selected problems."""
    resolved_output_dir = output_dir if output_dir.is_absolute() else workspace / output_dir
    result = build_pack_for_problem_ids(
        problem_ids,
        pack_id,
        platform_id or current_platform_id(),
        resolved_output_dir,
        workspace,
        verify_profile,
        solution_checks=solution_checks,
        warmup_profile=SOLUTION_WARMUP_PROFILE,
    )
    return {
        "archivePath": str(result.archive_path),
        "archiveLabel": rel(result.archive_path, workspace),
        "packId": result.pack_id,
        "platformId": result.platform_id,
        "problems": result.problems,
        "solutionChecks": result.solution_checks,
    }
