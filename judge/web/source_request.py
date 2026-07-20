"""소스 요청 웹 백엔드 구성과 응답 데이터 조립을 담당합니다."""

from __future__ import annotations

import contextlib
import tempfile
from collections.abc import Iterable
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.paths import ensure_inside
from judge.web.source_history_paths import source_history_root
from judge.web.source_history_store import save_existing_source, save_text_source


def source_path_from_request(
    problem_id: str,
    source_mode: str,
    source_path: str | None,
    source_text: str | None,
    filename: str | None,
    language: str | None = None,
    allowed_source_roots: Iterable[Path | str] | None = None,
) -> Path:
    roots = tuple(
        Path(root).expanduser().resolve()
        for root in (
            allowed_source_roots
            if allowed_source_roots is not None
            else (source_history_root(), Path(tempfile.gettempdir()))
        )
    )

    def allowed_existing_file(value: str, label: str) -> Path:
        candidate = Path(value).expanduser()
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise JudgeError(f"{label} file not found: {candidate}") from exc
        if not resolved.is_file():
            raise JudgeError(f"{label} must be a regular file: {candidate}")
        if not any(resolved == root or root in resolved.parents for root in roots):
            raise JudgeError(
                f"{label} must be inside an approved temporary or source-history directory"
            )
        return resolved

    if source_mode == "path":
        if not source_path:
            raise JudgeError("source path is required")
        path = allowed_existing_file(source_path, "source")
        return save_existing_source(path, problem_id, "path", language)

    if source_mode == "upload":
        if not source_path:
            raise JudgeError("uploaded source path is required")
        path = allowed_existing_file(source_path, "uploaded source")
        with contextlib.suppress(JudgeError):
            return ensure_inside(path, source_history_root())
        return save_existing_source(path, problem_id, "upload", language)

    if not source_text:
        raise JudgeError("source text is required")
    return save_text_source(source_text, filename, problem_id, language)
