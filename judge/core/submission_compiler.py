"""submission_compiler 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from judge.core.compiler_common import (
    CPP_SUFFIXES,
    PYTHON_SUFFIXES,
    SUPPORTED_USER_SUFFIXES,
    PreparedSubmission,
    compile_cpp,
    compile_error_message,
    java_main_class,
    resolve_tool,
)
from judge.core.errors import JudgeError
from judge.core.paths import rel, repo_root
from judge.utils.fs import write_json
from judge.utils.process import run_command


def compile_cpp_submission(source: Path, run_dir: Path, timeout_ms: int, root: Path) -> list[str]:
    """compile_cpp_submission 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source (Path): `source` 값입니다.
        run_dir (Path): `run_dir` 값입니다.
        timeout_ms (int): `timeout_ms` 값입니다.
        root (Path): `root` 값입니다.
    
    Returns:
        list[str]: 처리 결과를 반환합니다.
    """
    output = run_dir / "user_cpp"
    log_path = run_dir / "compile.log"
    compile_cpp(source, output, root, timeout_ms, log_path)
    return [str(output)]


def prepare_python_submission(source: Path) -> list[str]:
    """prepare_python_submission 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source (Path): `source` 값입니다.
    
    Returns:
        list[str]: 처리 결과를 반환합니다.
    """
    python = os.environ.get("ALJ_PYTHON")
    executable_name = Path(sys.executable).name.lower()
    compiled_runtime = getattr(sys, "frozen", False) or "__compiled__" in globals()
    if python is None and not compiled_runtime and "python" in executable_name:
        python = sys.executable
    if python is None:
        python = resolve_tool("ALJ_PYTHON", ["python3", "python"])
    return [python, str(source)]


def compile_java_submission(source: Path, run_dir: Path, timeout_ms: int) -> list[str]:
    """compile_java_submission 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source (Path): `source` 값입니다.
        run_dir (Path): `run_dir` 값입니다.
        timeout_ms (int): `timeout_ms` 값입니다.
    
    Returns:
        list[str]: 처리 결과를 반환합니다.
    """
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
        stderr = log_path.read_bytes() if log_path.exists() else b""
        raise JudgeError(compile_error_message("java compile failed", source, log_path, stderr))
    return [java, "-cp", str(classes_dir), java_main_class(source)]


def prepare_user_submission(
    source: Path, run_dir: Path, timeout_ms: int, root: Path | None = None
) -> PreparedSubmission:
    """prepare_user_submission 함수를 실행하고 결과를 반환합니다.
    
    Args:
        source (Path): `source` 값입니다.
        run_dir (Path): `run_dir` 값입니다.
        timeout_ms (int): `timeout_ms` 값입니다.
        root (Path | None): `root` 값입니다.
    
    Returns:
        PreparedSubmission: 처리 결과를 반환합니다.
    """
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
        detail = f"compile error\nlog: {rel(log_path, root)}"
        if str(exc):
            detail += f"\n\n{exc}"
        raise JudgeError(detail) from exc
