"""Product import boundaries for judge, Problem Studio, and shared core."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = {
    "judge": ROOT / "judge",
    "problem_studio": ROOT / "problem_studio",
    "alj_core": ROOT / "alj_core",
}
FORBIDDEN_IMPORTS = {
    "judge": {"problem_studio"},
    "problem_studio": {"judge"},
    "alj_core": {"judge", "problem_studio"},
}


def imported_root(name: str) -> str:
    return name.split(".", 1)[0]


def iter_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append((node.lineno, node.module))
    return imports


class ImportBoundaryTest(unittest.TestCase):
    def test_product_packages_do_not_import_each_other(self) -> None:
        violations = []
        for package, source_root in SOURCE_ROOTS.items():
            forbidden = FORBIDDEN_IMPORTS[package]
            for path in sorted(source_root.rglob("*.py")):
                for line, module in iter_imports(path):
                    if imported_root(module) in forbidden:
                        violations.append(
                            f"{path.relative_to(ROOT)}:{line}: {module}"
                        )

        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
