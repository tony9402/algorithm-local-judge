from __future__ import annotations

from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.paths import rel
from judge.utils.process import run_command

PROCESS_OUTPUT_LIMIT = 4000
INPUT_PREVIEW_BYTES = 4096
INPUT_PREVIEW_LINES = 12


def compact_process_output(stderr: bytes) -> str:
    """Return stderr as readable, bounded text."""
    text = stderr.decode("utf-8", errors="replace").strip()
    if len(text) > PROCESS_OUTPUT_LIMIT:
        return f"...truncated...\n{text[-PROCESS_OUTPUT_LIMIT:]}"
    return text


def input_preview(input_path: Path) -> str:
    """Return a line-numbered preview of a generated input file."""
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
    """Return a short hint for common testlib validator errors."""
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
    """Build a detailed validator failure message for CLI and web surfaces."""
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
    """Run the validator against a generated input file."""
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
    """Run the reference solution and write the expected answer file."""
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
    """Run the checker and return its exit code plus stderr message."""
    code, _, stderr = run_command(
        [str(checker), str(input_path), str(output_path), str(answer_path)], timeout_ms
    )
    return code, stderr.decode("utf-8", errors="replace")
