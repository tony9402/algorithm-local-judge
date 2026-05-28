"""제출 컴파일러 도메인 로직과 파일시스템 변경 정책을 담당합니다.
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
    """cpp 제출 소스와 설정을 실행 가능한 산출물과 진단 정보로 변환합니다.

    Args:
        source (Path): 원격 저장소 주소, 로컬 소스 경로, 또는 사용자가 제출한 소스 입력입니다.
        run_dir (Path): 실행 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        timeout_ms (int): 외부 프로세스가 끝나야 하는 제한 시간입니다. 단위는 밀리초입니다.
        root (Path): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.

    Returns:
        list[str]: 호출자가 순회하거나 화면에 표시할 cpp 제출 항목 목록입니다.
    """
    output = run_dir / "user_cpp"
    log_path = run_dir / "compile.log"
    compile_cpp(source, output, root, timeout_ms, log_path)
    return [str(output)]


def prepare_python_submission(source: Path) -> list[str]:
    python = os.environ.get("ALJ_PYTHON")
    executable_name = Path(sys.executable).name.lower()
    compiled_runtime = getattr(sys, "frozen", False) or "__compiled__" in globals()
    if python is None and not compiled_runtime and "python" in executable_name:
        python = sys.executable
    if python is None:
        python = resolve_tool("ALJ_PYTHON", ["python3", "python"])
    return [python, str(source)]


def compile_java_submission(source: Path, run_dir: Path, timeout_ms: int) -> list[str]:
    """java 제출 실행에 필요한 명령을 만들고 프로세스 종료 상태와 오류 출력을 해석합니다.

    Args:
        source (Path): 원격 저장소 주소, 로컬 소스 경로, 또는 사용자가 제출한 소스 입력입니다.
        run_dir (Path): 실행 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
        timeout_ms (int): 외부 프로세스가 끝나야 하는 제한 시간입니다. 단위는 밀리초입니다.

    Returns:
        list[str]: 호출자가 순회하거나 화면에 표시할 java 제출 항목 목록입니다.
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
    """prepare user 제출 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

        Args:
            source (Path): 원격 저장소 주소, 로컬 소스 경로, 또는 사용자가 제출한 소스 입력입니다.
            run_dir (Path): 실행 dir를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.
            timeout_ms (int): 외부 프로세스가 끝나야 하는 제한 시간입니다. 단위는 밀리초입니다.
            root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.
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
