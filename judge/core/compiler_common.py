from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from judge.core.config import COMPILE_FLAGS
from judge.core.errors import JudgeError
from judge.core.paths import rel
from judge.utils.process import run_command

CPP_SUFFIXES = {".cpp", ".cc", ".cxx"}
PYTHON_SUFFIXES = {".py"}
JAVA_SUFFIXES = {".java"}
SUPPORTED_USER_SUFFIXES = CPP_SUFFIXES | PYTHON_SUFFIXES | JAVA_SUFFIXES
JAVA_PUBLIC_CLASS_RE = re.compile(r"\bpublic\s+class\s+([A-Za-z_][A-Za-z0-9_]*)")
COMPILE_OUTPUT_LIMIT = 6000


@dataclass(frozen=True)
class PreparedSubmission:
    """Executable command and metadata for a prepared user submission."""

    command: list[str]
    language: str


def compile_cpp(
    source: Path, output: Path, include_root: Path, timeout_ms: int, log_path: Path
) -> dict[str, Any]:
    """Compile a C++ source file into an executable."""
    include_paths = [include_root]
    problems_include = include_root / "problems"
    if problems_include.exists():
        include_paths.append(problems_include)
    command = [
        "g++",
        *COMPILE_FLAGS,
        *(flag for include_path in include_paths for flag in ("-I", str(include_path))),
        str(source),
        "-o",
        str(output),
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    code, _, stderr = run_command(command, timeout_ms, log_path=log_path)
    if code != 0:
        raise JudgeError(compile_error_message("compile failed", source, log_path, stderr))
    return {"command": command, "stderr": stderr.decode("utf-8", errors="replace")}


def compile_error_message(label: str, source: Path, log_path: Path, stderr: bytes) -> str:
    """Build a compile failure message with the useful compiler output inline."""
    text = stderr.decode("utf-8", errors="replace").strip()
    if len(text) > COMPILE_OUTPUT_LIMIT:
        text = text[-COMPILE_OUTPUT_LIMIT:]
        text = f"...truncated...\n{text}"
    message = f"{label}: {rel(source)}\nlog: {rel(log_path)}"
    if text:
        message += f"\n\ncompiler output:\n{text}"
    return message


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
