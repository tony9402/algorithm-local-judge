from __future__ import annotations

import contextlib
import time
from pathlib import Path

from judge.core.errors import JudgeError
from judge.core.paths import cache_root, ensure_inside, validate_safe_id


def source_history_root() -> Path:
    """Return the cache directory that stores source files submitted from the web UI."""
    return cache_root() / "web-submissions"


def source_entry_dir(source_id: str) -> Path:
    """Return a validated source history entry directory."""
    validate_safe_id("source id", source_id)
    return ensure_inside(source_history_root() / source_id, cache_root())


def default_filename(problem_id: str, filename: str | None) -> str:
    """Return a safe filename for pasted source code."""
    if filename:
        name = Path(filename).name
    else:
        name = f"main-{problem_id}.py"
    if not name or name in {".", ".."}:
        raise JudgeError("invalid source filename")
    return name


def create_source_target(problem_id: str, filename: str | None) -> tuple[str, Path]:
    """Create a new source history target path for a submitted source file."""
    validate_safe_id("problem id", problem_id)
    source_id = str(time.time_ns())
    target_dir = source_entry_dir(source_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    return source_id, target_dir / default_filename(problem_id, filename)


def source_id_from_path(source: Path) -> str | None:
    """Return the source history id for a cached source path when available."""
    with contextlib.suppress(JudgeError):
        cached_source = ensure_inside(source, source_history_root())
        if cached_source.parent.parent == source_history_root():
            return cached_source.parent.name
    return None
