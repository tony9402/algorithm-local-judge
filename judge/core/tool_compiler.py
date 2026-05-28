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
    """Compile one problem tool and return its executable path."""
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
    """Compile generator, validator, checker, and reference solution."""
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
