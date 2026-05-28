"""검증기, 기준 솔루션, 체커 실행을 담당하는 저지 런타임 유틸리티입니다.
"""
from __future__ import annotations

from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.paths import rel
from judge.utils.process import run_command

PROCESS_OUTPUT_LIMIT = 4000
INPUT_PREVIEW_BYTES = 4096
INPUT_PREVIEW_LINES = 12


def compact_process_output(stderr: bytes) -> str:
    """외부 프로세스 stderr를 UTF-8 텍스트로 바꾸고 너무 긴 내용은 마지막 부분만 남깁니다.

    Args:
        stderr (bytes): 외부 프로세스가 표준 오류로 출력한 바이트 데이터입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 compact 프로세스 출력 문자열입니다.
    """
    text = stderr.decode("utf-8", errors="replace").strip()
    if len(text) > PROCESS_OUTPUT_LIMIT:
        return f"...truncated...\n{text[-PROCESS_OUTPUT_LIMIT:]}"
    return text


def input_preview(input_path: Path) -> str:
    """생성된 입력 파일 앞부분을 줄 번호가 붙은 미리보기 문자열로 만듭니다.

    Args:
        input_path (Path): 검증기, 솔루션, 체커에 전달할 테스트 입력 파일입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 입력 미리보기 문자열입니다.
    """
    try:
        data = input_path.read_bytes()
    except OSError as exc:
        return f"input preview unavailable: {exc}"
    truncated = len(data) > INPUT_PREVIEW_BYTES
    text = data[:INPUT_PREVIEW_BYTES].decode("utf-8", errors="replace")
    lines = text.splitlines() or [""]
    preview_lines = lines[:INPUT_PREVIEW_LINES]
    rendered = [f"{index:>4} | {line}" for index, line in enumerate(preview_lines, start=1)]
    if len(lines) > INPUT_PREVIEW_LINES or truncated:
        rendered.append("     | ... preview truncated ...")
    return "\n".join(rendered)


def validator_hint(message: str) -> str:
    """testlib 검증 오류 메시지를 해석해 사용자가 확인할 지점을 짧게 안내합니다.

    Args:
        message (str): 사용자에게 표시하거나 커밋/진행 상태에 기록할 메시지입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 검증기 hint 문자열입니다.
    """
    lowered = message.lower()
    if "expected eof" in lowered:
        return (
            "hint: validator stopped reading before the generated input ended. "
            "Check whether validator.cpp reads every value that generator.cpp writes."
        )
    if "expected eoln" in lowered:
        return "hint: validator expected the current line to end here. Check spaces/newlines."
    if "not in range" in lowered or "violates" in lowered:
        return "hint: generated value does not satisfy the validator constraint."
    return "hint: compare the generated input preview with the reads in validator.cpp."


def validator_error_message(
    input_path: Path,
    stderr: bytes,
    *,
    profile: str | None = None,
    case_index: int | None = None,
    case_total: int | None = None,
    root: Path | None = None,
) -> str:
    """검증 실패 원인, 케이스 위치, 입력 미리보기를 하나의 상세 오류 메시지로 구성합니다.

    Args:
        input_path (Path): 검증기, 솔루션, 체커에 전달할 테스트 입력 파일입니다.
        stderr (bytes): 외부 프로세스가 표준 오류로 출력한 바이트 데이터입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        case_index (int | None): 현재 처리 중인 케이스의 1부터 시작하는 순번입니다.
        case_total (int | None): 현재 프로필에서 처리할 전체 케이스 수입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 검증기 오류 message 문자열입니다.
    """
    reason = compact_process_output(stderr) or "validator exited with a non-zero status"
    case_label = f"{case_index}/{case_total}" if case_index and case_total else input_path.name
    context = []
    if profile:
        context.append(f"profile: {profile}")
    context.append(f"case: {case_label}")
    context.append(f"input: {rel(input_path, root)}")
    return "\n".join(
        [
            f"validator failed for {input_path.name}: {reason}",
            *context,
            validator_hint(reason),
            "",
            "input preview:",
            input_preview(input_path),
        ]
    )


def validator_check(
    validator: Path,
    input_path: Path,
    timeout_ms: int,
    *,
    profile: str | None = None,
    case_index: int | None = None,
    case_total: int | None = None,
    root: Path | None = None,
) -> None:
    """생성된 입력 파일을 검증기에 전달하고 실패하면 상세 메시지를 포함한 JudgeError를 발생시킵니다.

    Args:
        validator (Path): 생성된 입력이 제약을 만족하는지 검사할 검증기 실행 파일입니다.
        input_path (Path): 검증기, 솔루션, 체커에 전달할 테스트 입력 파일입니다.
        timeout_ms (int): 외부 프로세스가 끝나야 하는 제한 시간입니다. 단위는 밀리초입니다.
        profile (str | None): cases.yml에서 선택할 실행 또는 생성 프로필 이름입니다.
        case_index (int | None): 현재 처리 중인 케이스의 1부터 시작하는 순번입니다.
        case_total (int | None): 현재 프로필에서 처리할 전체 케이스 수입니다.
        root (Path | None): 상대 경로 계산과 안전성 검증의 기준이 되는 루트 경로입니다.
    """
    code, _, stderr = run_command([str(validator)], timeout_ms, input_path=input_path)
    if code != 0:
        raise JudgeError(
            validator_error_message(
                input_path,
                stderr,
                profile=profile,
                case_index=case_index,
                case_total=case_total,
                root=root,
            )
        )


def solution_write(solution: Path, input_path: Path, answer_path: Path, timeout_ms: int) -> None:
    """기준 솔루션을 실행해 테스트 입력에 대한 정답 출력 파일을 작성합니다.

    Args:
        solution (Path): 정답 또는 비교 대상 출력을 만드는 솔루션 실행 파일입니다.
        input_path (Path): 검증기, 솔루션, 체커에 전달할 테스트 입력 파일입니다.
        answer_path (Path): 기준 솔루션이 생성한 정답 출력 파일입니다.
        timeout_ms (int): 외부 프로세스가 끝나야 하는 제한 시간입니다. 단위는 밀리초입니다.
    """
    code, _, stderr = run_command(
        [str(solution)], timeout_ms, input_path=input_path, output_path=answer_path
    )
    if code != 0:
        raise JudgeError(
            f"solution failed for {input_path.name}: {stderr.decode('utf-8', errors='replace')}"
        )


def checker_compare(
    checker: Path, input_path: Path, output_path: Path, answer_path: Path, timeout_ms: int
) -> tuple[int, str]:
    """체커에 입력, 실제 출력, 정답 출력을 전달해 종료 코드와 오류 메시지를 받습니다.

    Args:
        checker (Path): 입력, 제출 출력, 정답 출력을 비교하는 체커 실행 파일입니다.
        input_path (Path): 검증기, 솔루션, 체커에 전달할 테스트 입력 파일입니다.
        output_path (Path): 제출 프로그램이 생성한 실제 출력 파일입니다.
        answer_path (Path): 기준 솔루션이 생성한 정답 출력 파일입니다.
        timeout_ms (int): 외부 프로세스가 끝나야 하는 제한 시간입니다. 단위는 밀리초입니다.

    Returns:
        tuple[int, str]: 체커 compare 판단에 필요한 여러 값을 정해진 순서로 묶은 튜플입니다.
    """
    code, _, stderr = run_command(
        [str(checker), str(input_path), str(output_path), str(answer_path)], timeout_ms
    )
    return code, stderr.decode("utf-8", errors="replace")
