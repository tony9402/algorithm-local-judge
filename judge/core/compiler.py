from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from judge.core.config import COMPILE_FLAGS
from judge.core.errors import JudgeError
from judge.core.paths import build_root, rel, repo_root
from judge.core.problem import TOOL_NAMES, is_precompiled_problem, tool_output_path, tool_paths
from judge.utils.fs import write_json
from judge.utils.process import run_command

CPP_SUFFIXES = {".cpp", ".cc", ".cxx"}
PYTHON_SUFFIXES = {".py"}
JAVA_SUFFIXES = {".java"}
SUPPORTED_USER_SUFFIXES = CPP_SUFFIXES | PYTHON_SUFFIXES | JAVA_SUFFIXES
JAVA_PUBLIC_CLASS_RE = re.compile(r"\bpublic\s+class\s+([A-Za-z_][A-Za-z0-9_]*)")


@dataclass(frozen=True)
class PreparedSubmission:
    """Executable command and metadata for a prepared user submission."""

    command: list[str]
    language: str


def compile_cpp(
    source: Path, output: Path, include_root: Path, timeout_ms: int, log_path: Path
) -> dict[str, Any]:
    """Compile a C++ source file into an executable."""
    command = [
        "g++",
        *COMPILE_FLAGS,
        "-I",
        str(include_root),
        str(source),
        "-o",
        str(output),
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    code, _, stderr = run_command(command, timeout_ms, log_path=log_path)
    if code != 0:
        raise JudgeError(f"compile failed: {rel(source)}\nlog: {rel(log_path)}")
    return {"command": command, "stderr": stderr.decode("utf-8", errors="replace")}


def compile_problem_tools(problem_id: str, root: Path | None = None) -> dict[str, Path]:
    """Compile generator, validator, checker, and reference solution."""
    _, _, metadata, paths = tool_paths(problem_id, root)
    if is_precompiled_problem(metadata):
        return {name: paths[name] for name in TOOL_NAMES}

    root = root or repo_root()
    limits = metadata.get("limits", {})
    timeout_ms = limits.get("compileTimeoutMs", 5000)
    logs = build_root(root) / "tools" / problem_id / "logs"
    outputs = {
        "generator": tool_output_path(problem_id, "generator", root),
        "validator": tool_output_path(problem_id, "validator", root),
        "checker": tool_output_path(problem_id, "checker", root),
        "solution": tool_output_path(problem_id, "solution", root),
    }
    for name in TOOL_NAMES:
        compile_cpp(paths[name], outputs[name], root, timeout_ms, logs / f"{name}.log")
    return outputs


def resolve_tool(env_name: str, candidates: list[str]) -> str:
    """Resolve a language tool from an environment variable or PATH."""
    configured = os.environ.get(env_name)
    if configured:
        return configured
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise JudgeError(
        f"required tool not found. Set {env_name} or install one of: {', '.join(candidates)}"
    )


def java_main_class(source: Path) -> str:
    """Return the Java class name to execute for a source file."""
    match = JAVA_PUBLIC_CLASS_RE.search(source.read_text(encoding="utf-8", errors="replace"))
    if match:
        return match.group(1)
    return source.stem


def compile_cpp_submission(source: Path, run_dir: Path, timeout_ms: int, root: Path) -> list[str]:
    """Compile a user's C++ submission and return its execution command."""
    output = run_dir / "user_cpp"
    log_path = run_dir / "compile.log"
    compile_cpp(source, output, root, timeout_ms, log_path)
    return [str(output)]


def prepare_python_submission(source: Path) -> list[str]:
    """Return the execution command for a Python submission."""
    python = os.environ.get("ALJ_PYTHON")
    executable_name = Path(sys.executable).name.lower()
    compiled_runtime = getattr(sys, "frozen", False) or "__compiled__" in globals()
    if python is None and not compiled_runtime and "python" in executable_name:
        python = sys.executable
    if python is None:
        python = resolve_tool("ALJ_PYTHON", ["python3", "python"])
    return [python, str(source)]


def compile_java_submission(source: Path, run_dir: Path, timeout_ms: int) -> list[str]:
    """Compile a user's Java submission and return its execution command."""
    javac = resolve_tool("ALJ_JAVAC", ["javac"])
    java = resolve_tool("ALJ_JAVA", ["java"])
    classes_dir = run_dir / "classes"
    log_path = run_dir / "compile.log"
    classes_dir.mkdir(parents=True, exist_ok=True)
    code, _, _ = run_command(
        [javac, "-encoding", "UTF-8", "-d", str(classes_dir), str(source)],
        timeout_ms,
        log_path=log_path,
    )
    if code != 0:
        raise JudgeError(f"java compile failed: {rel(source)}\nlog: {rel(log_path)}")
    return [java, "-cp", str(classes_dir), java_main_class(source)]


def prepare_user_submission(
    source: Path, run_dir: Path, timeout_ms: int, root: Path | None = None
) -> PreparedSubmission:
    """Compile or wrap a user submission and return the command to execute."""
    root = root or repo_root()
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_USER_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_USER_SUFFIXES))
        raise JudgeError(f"unsupported source extension: {source.suffix} (supported: {supported})")
    try:
        if suffix in CPP_SUFFIXES:
            return PreparedSubmission(
                compile_cpp_submission(source, run_dir, timeout_ms, root), "cpp"
            )
        if suffix in PYTHON_SUFFIXES:
            return PreparedSubmission(prepare_python_submission(source), "python")
        return PreparedSubmission(compile_java_submission(source, run_dir, timeout_ms), "java")
    except JudgeError as exc:
        log_path = run_dir / "compile.log"
        if not log_path.exists():
            log_path.write_text(str(exc) + "\n", encoding="utf-8")
        write_json(
            run_dir / "result.json", {"status": "compile_error", "compileLog": str(log_path)}
        )
        raise JudgeError(f"compile error\nlog: {rel(log_path, root)}") from exc
