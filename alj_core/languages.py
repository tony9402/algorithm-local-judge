"""Submission language normalization shared by CLI, web, and judge runtime."""

from __future__ import annotations

from pathlib import Path

LANGUAGE_OPTIONS = {
    "cpp": {"display": "C++", "default": "main.cpp", "extensions": {".cpp", ".cc", ".cxx"}},
    "python": {"display": "Python", "default": "main.py", "extensions": {".py"}},
    "pypy": {"display": "PyPy", "default": "main.py", "extensions": {".py"}},
    "java": {"display": "Java", "default": "Main.java", "extensions": {".java"}},
}

LANGUAGE_ALIASES = {
    "c++": "cpp",
    "cpp": "cpp",
    "py": "python",
    "python": "python",
    "python3": "python",
    "pypy": "pypy",
    "pypy3": "pypy",
    "java": "java",
}


def normalize_language_id(language: str | None) -> str | None:
    normalized = (language or "").strip().lower()
    if not normalized:
        return None
    return LANGUAGE_ALIASES.get(normalized)


def language_id_from_filename(filename: str) -> str | None:
    suffix = Path(filename).suffix.lower()
    for language_id, spec in LANGUAGE_OPTIONS.items():
        if language_id == "pypy":
            continue
        if suffix in spec["extensions"]:
            return language_id
    return None


def language_display(language: str | None) -> str:
    language_id = normalize_language_id(language)
    if language_id and language_id in LANGUAGE_OPTIONS:
        return str(LANGUAGE_OPTIONS[language_id]["display"])
    return "Unknown"


def language_extensions(language: str) -> set[str]:
    spec = LANGUAGE_OPTIONS.get(language)
    if not spec:
        return set()
    return set(spec["extensions"])


def language_default_filename(language: str) -> str:
    return str(LANGUAGE_OPTIONS[language]["default"])
