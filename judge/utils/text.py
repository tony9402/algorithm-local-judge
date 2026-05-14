from __future__ import annotations

from pathlib import Path


def format_size(size: int) -> str:
    """Format a byte count with binary units."""
    units = ["B", "KiB", "MiB", "GiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024


def preview(path: Path, max_chars: int = 4000) -> str:
    """Read a text file and truncate it for terminal preview output."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n... truncated ...\n"
    return text
