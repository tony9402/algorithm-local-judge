from __future__ import annotations

from pathlib import Path
from typing import Any

from judge.core.config import FORBIDDEN_METADATA_KEYS
from judge.core.errors import JudgeError
from judge.core.paths import build_root, problem_pack_root, rel, repo_root, validate_safe_id
from judge.utils.fs import read_json

TOOL_NAMES = ["generator", "validator", "checker", "solution"]
REQUIRED_TOOL_FIELDS = [*TOOL_NAMES, "generatorConfig"]
PRECOMPILED_TOOL_MODE = "precompiled"


def forbidden_metadata_keys(metadata: dict[str, Any]) -> set[str]:
    """Return metadata keys that look like external platform identifiers."""
    forbidden = set()
    for key in metadata:
        lowered = key.lower()
        if key in FORBIDDEN_METADATA_KEYS:
            forbidden.add(key)
        elif key != "problemId" and (
            lowered.endswith("id") or "platform" in lowered or "url" in lowered
        ):
            forbidden.add(key)
    return forbidden


def load_problem(problem_id: str, root: Path | None = None) -> tuple[Path, Path, dict[str, Any]]:
    """Load and validate a problem metadata file."""
    validate_safe_id("problem id", problem_id)
    problem_dir = find_problem_dir(problem_id, root)
    display_root = root or repo_root()
    metadata_path = problem_dir / "problem.json"
    if not metadata_path.exists():
        raise JudgeError(f"problem metadata not found: {rel(metadata_path, display_root)}")
    metadata = read_json(metadata_path)
    forbidden = sorted(forbidden_metadata_keys(metadata))
    if forbidden:
        path_label = rel(metadata_path, display_root)
        raise JudgeError(f"forbidden metadata keys in {path_label}: {', '.join(forbidden)}")
    if metadata.get("problemId") != problem_id:
        raise JudgeError(f"problemId mismatch in {rel(metadata_path, display_root)}")
    return problem_dir, metadata_path, metadata


def installed_problem_roots() -> list[Path]:
    """Return all problem directories contributed by installed problem packs."""
    packs_root = problem_pack_root()
    if not packs_root.exists():
        return []
    return [
        pack_dir / "problems"
        for pack_dir in sorted(path for path in packs_root.iterdir() if path.is_dir())
        if (pack_dir / "problems").exists()
    ]


def problem_roots(root: Path | None = None) -> list[Path]:
    """Return candidate roots that may contain problem directories."""
    if root is not None:
        return [root / "problems"]
    roots = []
    development_root = repo_root() / "problems"
    if development_root.exists():
        roots.append(development_root)
    roots.extend(installed_problem_roots())
    return roots


def find_problem_dir(problem_id: str, root: Path | None = None) -> Path:
    """Find the directory for a problem in development roots or installed packs."""
    validate_safe_id("problem id", problem_id)
    for problems_dir in problem_roots(root):
        problem_dir = problems_dir / problem_id
        if (problem_dir / "problem.json").exists():
            return problem_dir
    base = root or repo_root()
    raise JudgeError(f"problem metadata not found: {rel(base / 'problems' / problem_id)}")


def is_precompiled_problem(metadata: dict[str, Any]) -> bool:
    """Return whether problem tools are already compiled in the problem metadata."""
    tools = metadata.get("tools", {})
    return tools.get("mode") == PRECOMPILED_TOOL_MODE


def tool_paths(
    problem_id: str, root: Path | None = None
) -> tuple[Path, Path, dict[str, Any], dict[str, Path]]:
    """Resolve and validate all tool paths declared by a problem."""
    display_root = root or repo_root()
    problem_dir, metadata_path, metadata = load_problem(problem_id, root)
    tools = metadata.get("tools", {})
    missing = [name for name in REQUIRED_TOOL_FIELDS if name not in tools]
    if missing:
        raise JudgeError(f"missing tool path(s): {', '.join(missing)}")
    paths = {}
    problem_root = problem_dir.resolve()
    for name in REQUIRED_TOOL_FIELDS:
        raw_path = Path(tools[name])
        if raw_path.is_absolute() or ".." in raw_path.parts:
            raise JudgeError(f"unsafe {name} path in metadata: {tools[name]}")
        path = (problem_dir / raw_path).resolve()
        if not (path == problem_root or problem_root in path.parents):
            raise JudgeError(f"{name} path escapes problem directory: {tools[name]}")
        paths[name] = path
    for name, path in paths.items():
        if not path.exists():
            raise JudgeError(f"{name} not found: {rel(path, display_root)}")
    return problem_dir, metadata_path, metadata, paths


def tool_output_path(problem_id: str, name: str, root: Path | None = None) -> Path:
    """Return the compiled binary path for a named problem tool."""
    return build_root(root) / "tools" / problem_id / name


def problem_sort_key(problem_id: str) -> tuple[Any, ...]:
    """Sort numeric problem ids naturally before non-numeric ids."""
    if problem_id.isdigit():
        return (0, int(problem_id), problem_id)
    return (1, problem_id)


def discover_problem_ids(root: Path | None = None) -> list[str]:
    """Discover problem ids from `problems/*/problem.json`."""
    problem_ids = set()
    for problems_dir in problem_roots(root):
        if not problems_dir.exists():
            continue
        problem_ids.update(path.parent.name for path in problems_dir.glob("*/problem.json"))
    return sorted(
        problem_ids,
        key=problem_sort_key,
    )


def validate_problem_sequence(problem_ids: list[str]) -> list[str]:
    """Validate that numeric problem ids start at 1 and have no gaps."""
    errors = []
    if not problem_ids:
        return ["no problems found"]

    numbers = []
    seen = {}
    for problem_id in problem_ids:
        if not problem_id.isdigit():
            errors.append(f"problem id must be numeric: {problem_id}")
            continue
        number = int(problem_id)
        numbers.append(number)
        seen.setdefault(number, []).append(problem_id)

    for number, ids in sorted(seen.items()):
        if len(ids) > 1:
            errors.append(f"duplicate numeric problem id {number}: {', '.join(ids)}")

    if numbers:
        expected = set(range(1, max(numbers) + 1))
        actual = set(numbers)
        missing = sorted(expected - actual)
        if 1 not in actual:
            errors.append("problem numbering must start at 1")
        if missing:
            errors.append(
                "missing problem number(s): " + ", ".join(str(number) for number in missing)
            )

    return errors
