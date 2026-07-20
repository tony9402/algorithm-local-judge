"""제출 컴파일러 도메인 로직과 파일시스템 변경 정책을 담당합니다."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from alj_core.compiler_common import (
    CPP_SUFFIXES,
    PYTHON_SUFFIXES,
    SUPPORTED_USER_SUFFIXES,
    PreparedSubmission,
    compile_cpp,
    compile_error_message,
    compiler_identity,
    java_main_class,
    resolve_tool,
)
from alj_core.config import COMPILE_FLAGS, PROTOCOL_VERSION
from alj_core.errors import JudgeError, SubmissionCompileError
from alj_core.languages import language_extensions, normalize_language_id
from alj_core.paths import cache_root, rel, repo_root
from alj_core.utils.fs import read_json, write_json
from alj_core.utils.hashing import sha256_file, sha256_json
from alj_core.utils.process import run_command

_SUBMISSION_COMPILE_LOCK = threading.Lock()


def _submission_cache_dir(
    source: Path,
    language: str,
    timeout_ms: int,
    root: Path,
    *,
    compiler: dict[str, object] | None = None,
) -> Path:
    payload = {
        "protocolVersion": PROTOCOL_VERSION,
        "language": language,
        "source": source.name,
        "sourceHash": sha256_file(source),
        "timeoutMs": timeout_ms,
        "compileFlags": COMPILE_FLAGS if language == "cpp" else [],
        "compiler": compiler,
    }
    return cache_root(root) / "submissions" / sha256_json(payload)[:24]


def _valid_submission_cache(
    cache_dir: Path,
    language: str,
    output: Path,
    *,
    required_outputs: list[Path] | None = None,
) -> bool:
    manifest_path = cache_dir / "manifest.json"
    if not output.exists() or not manifest_path.exists():
        return False
    if any(not path.exists() for path in required_outputs or []):
        return False
    try:
        manifest = read_json(manifest_path)
    except (json.JSONDecodeError, OSError):
        return False
    return manifest.get("language") == language and manifest.get("ok") is True


def _write_submission_manifest(cache_dir: Path, language: str, source: Path) -> None:
    write_json(
        cache_dir / "manifest.json",
        {
            "schemaVersion": 1,
            "language": language,
            "source": str(source),
            "sourceHash": sha256_file(source),
            "ok": True,
        },
    )


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
    cache_dir = _submission_cache_dir(
        source,
        "cpp",
        timeout_ms,
        root,
        compiler=compiler_identity("ALJ_CXX", ["g++"]),
    )
    output = cache_dir / "user_cpp"
    log_path = cache_dir / "compile.log"
    with _SUBMISSION_COMPILE_LOCK:
        if _valid_submission_cache(cache_dir, "cpp", output):
            return [str(output)]
        cache_dir.mkdir(parents=True, exist_ok=True)
        compile_cpp(source, output, root, timeout_ms, log_path)
        _write_submission_manifest(cache_dir, "cpp", source)
    return [str(output)]


def prepare_python_submission(source: Path, runtime: str = "python") -> list[str]:
    if runtime == "pypy":
        return [resolve_tool("ALJ_PYPY", ["pypy3", "pypy"]), str(source)]
    return [resolve_tool("ALJ_PYTHON", ["python3", "python"]), str(source)]


def compile_java_submission(source: Path, run_dir: Path, timeout_ms: int, root: Path) -> list[str]:
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
    main_class = java_main_class(source)
    cache_dir = _submission_cache_dir(
        source,
        "java",
        timeout_ms,
        root,
        compiler=compiler_identity("ALJ_JAVAC", ["javac"]),
    )
    classes_dir = cache_dir / "classes"
    main_class_file = classes_dir / f"{main_class.replace('.', '/')}.class"
    log_path = cache_dir / "compile.log"
    with _SUBMISSION_COMPILE_LOCK:
        if not _valid_submission_cache(
            cache_dir,
            "java",
            classes_dir,
            required_outputs=[main_class_file],
        ):
            classes_dir.mkdir(parents=True, exist_ok=True)
            code, _, _ = run_command(
                [javac, "-encoding", "UTF-8", "-d", str(classes_dir), str(source)],
                timeout_ms,
                log_path=log_path,
            )
            if code != 0:
                stderr = log_path.read_bytes() if log_path.exists() else b""
                raise JudgeError(
                    compile_error_message("java compile failed", source, log_path, stderr)
                )
            _write_submission_manifest(cache_dir, "java", source)
    return [java, "-cp", str(classes_dir), main_class]


def prepare_user_submission(
    source: Path,
    run_dir: Path,
    timeout_ms: int,
    root: Path | None = None,
    language: str | None = None,
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
    explicit_language = normalize_language_id(language)
    if language and explicit_language is None:
        raise JudgeError(f"unsupported submission language: {language}")
    if explicit_language and suffix not in language_extensions(explicit_language):
        allowed = ", ".join(sorted(language_extensions(explicit_language)))
        raise JudgeError(
            f"source extension {source.suffix} is not supported for {explicit_language} "
            f"(allowed: {allowed})"
        )
    try:
        if explicit_language == "cpp" or (explicit_language is None and suffix in CPP_SUFFIXES):
            return PreparedSubmission(
                compile_cpp_submission(source, run_dir, timeout_ms, root), "cpp"
            )
        if explicit_language in {"python", "pypy"} or (
            explicit_language is None and suffix in PYTHON_SUFFIXES
        ):
            runtime = explicit_language or "python"
            return PreparedSubmission(prepare_python_submission(source, runtime), runtime)
        return PreparedSubmission(
            compile_java_submission(source, run_dir, timeout_ms, root), "java"
        )
    except JudgeError as exc:
        log_path = run_dir / "compile.log"
        if not log_path.exists():
            log_path.write_text(str(exc) + "\n", encoding="utf-8")
        result = {
            "runId": run_dir.name,
            "status": "compile_error",
            "compileLog": str(log_path),
        }
        write_json(run_dir / "result.json", result)
        detail = f"compile error\nlog: {rel(log_path, root)}"
        if str(exc):
            detail += f"\n\n{exc}"
        raise SubmissionCompileError(
            detail,
            run_id=run_dir.name,
            result=result,
        ) from exc
