from __future__ import annotations

import subprocess
import time
from pathlib import Path

from tests.e2e.helpers import create_runnable_minimal_pack


def fake_compile_problem_tools(
    problem_id: str,
    root: Path | None = None,
    **_kwargs,
) -> dict[str, Path]:
    workspace = Path(root or ".").resolve()
    target = workspace / ".judge-cache" / "e2e-tools" / problem_id
    target.mkdir(parents=True, exist_ok=True)
    tools = {}
    for name in ["generator", "validator", "checker", "solution"]:
        path = target / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
        tools[name] = path
    return tools


def fake_validate_all_data(
    workspace: Path,
    problem_id: str,
    force: bool = False,
    progress=None,
    **_kwargs,
) -> dict:
    if progress is not None:
        progress("Compiling cases.yml for all profiles.")
        progress("Validating generated case sample_1 (1/1).")
        progress("Validating generated case hidden_1 (1/2).")
        progress("Validating generated case hidden_2 (2/2).")
    return {
        "problemId": problem_id,
        "profileCount": 2,
        "caseCount": 3,
        "profiles": [
            {"name": "sample", "caseCount": 1},
            {"name": "hidden", "caseCount": 2},
        ],
        "force": force,
    }


def fake_verify_solutions(
    workspace: Path,
    problem_id: str,
    profile: str = "hidden",
    progress=None,
    **_kwargs,
) -> dict:
    paths = _kwargs.get("solutions")
    if not paths:
        solution_dir = workspace / "problems" / problem_id / "solutions"
        paths = [
            path.relative_to(workspace / "problems" / problem_id).as_posix()
            for path in sorted(solution_dir.glob("*"))
        ] or ["solutions/main_solution.ac.cpp"]
    if progress is not None:
        progress(f"Running solution checks for {problem_id}.")
    return {
        "problemId": problem_id,
        "profile": profile,
        "passed": True,
        "verifiedCount": len(paths),
        "totalCount": len(paths),
        "skippedCount": 0,
        "checks": [
            {
                "path": path,
                "sourcePath": path,
                "expectedStatus": "accepted",
                "actualStatus": "accepted",
                "passed": True,
                "runId": "e2e-run",
                "metrics": {"maxTimeMs": 1, "maxMemoryBytes": 1024},
                "cases": [
                    {
                        "case": "hidden-1",
                        "status": "accepted",
                        "timeMs": 1,
                        "memoryBytes": 1024,
                    }
                ],
            }
            for path in paths
        ],
    }


def fake_build_problem_pack(
    workspace: Path,
    problem_id: str,
    pack_id: str,
    output_dir: Path,
    platform_id: str | None = None,
    verify_profile: str = "hidden",
    **_kwargs,
) -> dict:
    archive = workspace / output_dir / f"{pack_id}-e2e.aljpack"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"e2e-pack")
    return {
        "archivePath": str(archive),
        "archiveLabel": str(archive.relative_to(workspace)),
        "packId": pack_id,
        "platformId": platform_id or "e2e-platform",
        "verifyProfile": verify_profile,
        "problems": [problem_id],
        "solutionChecks": [],
    }


def fake_build_runnable_pack(
    workspace: Path,
    problem_id: str,
    pack_id: str,
    output_dir: Path,
    platform_id: str | None = None,
    verify_profile: str = "hidden",
    **_kwargs,
) -> dict:
    archive = workspace / output_dir / f"{pack_id}-{problem_id}-e2e.aljpack"
    create_runnable_minimal_pack(archive, pack_id=pack_id, problem_id=problem_id)
    return {
        "archivePath": str(archive),
        "archiveLabel": str(archive.relative_to(workspace)),
        "packId": pack_id,
        "platformId": platform_id or "e2e-platform",
        "verifyProfile": verify_profile,
        "problems": [problem_id],
        "solutionChecks": [],
    }


def fake_slow_build_runnable_pack(*args, **kwargs) -> dict:
    time.sleep(2.0)
    return fake_build_runnable_pack(*args, **kwargs)


def fake_cancellable_slow_build_runnable_pack(*args, cancel_token=None, **kwargs) -> dict:
    for _ in range(150):
        if cancel_token:
            cancel_token.check()
        time.sleep(0.1)
    return fake_build_runnable_pack(*args, **kwargs)


def fake_verify_solutions_mismatch(
    workspace: Path,
    problem_id: str,
    profile: str = "hidden",
    progress=None,
    **_kwargs,
) -> dict:
    result = fake_verify_solutions(workspace, problem_id, profile, progress, **_kwargs)
    result["passed"] = False
    if result["checks"]:
        result["checks"][0] = {
            **result["checks"][0],
            "actualStatus": "wrong_answer",
            "passed": False,
            "message": "forced mismatch",
        }
    return result


def fake_bulk_build(
    workspace: Path,
    pack_id: str,
    output_dir: Path,
    platform_id: str | None = None,
    verify_profile: str = "hidden",
    force: bool = False,
    progress=None,
    max_workers: int | None = None,
    problem_ids: list[str] | None = None,
    **_kwargs,
) -> dict:
    ids = problem_ids or ["alpha"]
    if progress is not None:
        for index, problem_id in enumerate(ids, start=1):
            progress(f"[{index}/{len(ids)}] Problem {problem_id}: Pack built: {pack_id}")
    return {
        "passed": True,
        "summary": f"{len(ids)}개 문제 전체 테스트 통과 · 1개 팩 생성",
        "problemCount": len(ids),
        "failedCount": 0,
        "packCount": 1,
        "force": force,
        "maxWorkers": max_workers,
        "verifyProfile": verify_profile,
        "platformId": platform_id or "e2e-platform",
        "problems": [
            {
                "problemId": problem_id,
                "passed": True,
                "summary": "ok",
                "pack": {"archiveLabel": f"dist/packs/{pack_id}-e2e.aljpack"},
            }
            for problem_id in ids
        ],
    }


def fake_slow_bulk_build(*args, cancel_token=None, **kwargs) -> dict:
    if cancel_token:
        cancel_token.check()
    time.sleep(2.0)
    if cancel_token:
        cancel_token.check()
    return fake_bulk_build(*args, **kwargs)


def fake_cancellable_slow_bulk_build(*args, cancel_token=None, **kwargs) -> dict:
    for _ in range(150):
        if cancel_token:
            cancel_token.check()
        time.sleep(0.1)
    return fake_bulk_build(*args, **kwargs)


def fake_bulk_build_partial(
    workspace: Path,
    pack_id: str,
    output_dir: Path,
    platform_id: str | None = None,
    verify_profile: str = "hidden",
    force: bool = False,
    progress=None,
    max_workers: int | None = None,
    problem_ids: list[str] | None = None,
    **_kwargs,
) -> dict:
    ids = problem_ids or ["alpha", "beta"]
    if progress is not None:
        for index, problem_id in enumerate(ids, start=1):
            status = "Pack built" if index == 1 else "Full test failed"
            progress(f"[{index}/{len(ids)}] Problem {problem_id}: {status}: forced")
    return {
        "passed": False,
        "summary": f"{len(ids)}개 중 1개 문제 실패 · 1개 팩 생성",
        "problemCount": len(ids),
        "failedCount": 1,
        "packCount": 1,
        "force": force,
        "maxWorkers": max_workers,
        "verifyProfile": verify_profile,
        "platformId": platform_id or "e2e-platform",
        "problems": [
            {
                "problemId": problem_id,
                "passed": index == 0,
                "summary": "ok" if index == 0 else "forced failure",
                "pack": (
                    {"archiveLabel": f"dist/packs/{pack_id}-{problem_id}.aljpack"}
                    if index == 0
                    else None
                ),
            }
            for index, problem_id in enumerate(ids)
        ],
    }


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()
