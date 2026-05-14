from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from judge.core.cases_compile import compile_cases_file, format_compile_result


class CasesCompileTest(unittest.TestCase):
    """Unit tests for cases.yml compilation diagnostics."""

    def write_cases_yaml(self, text: str) -> Path:
        """Write a temporary cases.yml fixture and return its path."""
        directory = tempfile.TemporaryDirectory(prefix="alj-cases-compile-")
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "cases.yml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_compiles_fixed_repeat_and_matrix_range(self) -> None:
        """Valid DSL entries should expand into concrete case summaries."""
        path = self.write_cases_yaml(
            """
profiles:
  sample:
    cases:
      - name: sample-1
        type: fixed
        content: |
          1 1
      - repeat:
          var: i
          from: 1
          to: 2
          item:
            name: "repeat-${i}"
            type: generator
            seed: "${100 + i}"
            args:
              minN: "${i}"
      - matrix:
          vars:
            n:
              range:
                from: 1
                to: 3
                step: 2
            m: [1, 2]
          where: "m <= n"
          item:
            name: "n-${n}-m-${m}"
            type: generator
            seed: "${1000 + n * 10 + m}"
            args:
              minN: "${n}"
              minM: "${m}"
""".lstrip()
        )

        result = compile_cases_file(path, "sample")

        self.assertTrue(result.valid, format_compile_result(result))
        self.assertEqual(len(result.profiles), 1)
        profile = result.profiles[0]
        self.assertEqual(profile.name, "sample")
        self.assertEqual(
            [case.name for case in profile.cases],
            [
                "sample-1",
                "repeat-1",
                "repeat-2",
                "n-1-m-1",
                "n-3-m-1",
                "n-3-m-2",
            ],
        )

    def test_matrix_null_reports_indentation_hint(self) -> None:
        """A mis-indented matrix block should not leak a NoneType generator error."""
        path = self.write_cases_yaml(
            """
profiles:
  hidden:
    cases:
      - matrix:
        vars:
          i:
            range:
              from: 1
              to: 3
        item:
          name: "hidden-${i:02d}"
          type: generator
          seed: "${1000 + i}"
""".lstrip()
        )

        result = compile_cases_file(path, "hidden")

        self.assertFalse(result.valid)
        diagnostic = result.diagnostics[0]
        self.assertEqual(diagnostic.profile, "hidden")
        self.assertEqual(diagnostic.location, "cases[0].matrix")
        self.assertEqual(diagnostic.line, 4)
        self.assertIn("matrix must be a mapping, got null", diagnostic.message)
        self.assertIn("matrix:", diagnostic.hint or "")
        self.assertIn("profile hidden, cases[0].matrix", format_compile_result(result))

    def test_unknown_expression_variable_is_diagnostic(self) -> None:
        """Expression failures should be converted into compile diagnostics."""
        path = self.write_cases_yaml(
            """
profiles:
  hidden:
    cases:
      - matrix:
          vars:
            t: [1]
          item:
            name: "hidden-${i:02d}"
            type: generator
            seed: "${1000 + t}"
""".lstrip()
        )

        result = compile_cases_file(path, "hidden")

        self.assertFalse(result.valid)
        self.assertEqual(result.diagnostics[0].profile, "hidden")
        self.assertEqual(result.diagnostics[0].location, "cases[0].matrix.item.name")
        self.assertIn("unknown variable: i", result.diagnostics[0].message)

    def test_schema_errors_are_collected_after_expansion(self) -> None:
        """Concrete case schema issues should be reported without generation."""
        path = self.write_cases_yaml(
            """
profiles:
  sample:
    cases:
      - name: "bad/name"
        type: generator
        seed: "one"
        args: []
      - name: "bad/name"
        type: unknown
""".lstrip()
        )

        result = compile_cases_file(path, "sample")
        messages = [item.message for item in result.diagnostics]

        self.assertFalse(result.valid)
        self.assertIn("unsafe case name: bad/name", messages)
        self.assertIn("generator case requires integer seed", messages)
        self.assertIn("generator args must be a mapping", messages)
        self.assertIn("unknown case type: unknown", messages)

    def test_duplicate_case_name_is_reported(self) -> None:
        """Duplicate safe case names should be reported directly."""
        path = self.write_cases_yaml(
            """
profiles:
  sample:
    cases:
      - name: same
        type: fixed
        content: ""
      - name: same
        type: fixed
        content: ""
""".lstrip()
        )

        result = compile_cases_file(path, "sample")

        self.assertFalse(result.valid)
        self.assertIn("duplicate case name: same", [item.message for item in result.diagnostics])

    def test_bool_seed_is_not_treated_as_integer(self) -> None:
        """YAML booleans should not satisfy integer seed validation."""
        path = self.write_cases_yaml(
            """
profiles:
  sample:
    cases:
      - name: bool-seed
        type: generator
        seed: true
""".lstrip()
        )

        result = compile_cases_file(path, "sample")

        self.assertFalse(result.valid)
        self.assertIn(
            "generator case requires integer seed",
            [item.message for item in result.diagnostics],
        )

    def test_fixed_and_template_scalar_types_are_validated(self) -> None:
        """Cases that would fail during rendering should fail at compile time."""
        path = self.write_cases_yaml(
            """
profiles:
  sample:
    cases:
      - name: bad-fixed
        type: fixed
        content: 123
      - name: bad-template
        type: template
        template: 123
        vars: []
""".lstrip()
        )

        result = compile_cases_file(path, "sample")
        messages = [item.message for item in result.diagnostics]

        self.assertFalse(result.valid)
        self.assertIn("fixed case content must be a string", messages)
        self.assertIn("template case template must be a string", messages)
        self.assertIn("template vars must be a mapping", messages)

    def test_null_args_vars_and_missing_type_are_reported(self) -> None:
        """Explicit null mappings and missing type should fail before rendering."""
        path = self.write_cases_yaml(
            """
profiles:
  sample:
    cases:
      - name: no-type
        content: ""
      - name: null-args
        type: generator
        seed: 1
        args:
      - name: null-vars
        type: template
        template: ""
        vars:
""".lstrip()
        )

        result = compile_cases_file(path, "sample")
        messages = [item.message for item in result.diagnostics]

        self.assertFalse(result.valid)
        self.assertIn("case type is required", messages)
        self.assertIn("generator args must be a mapping", messages)
        self.assertIn("template vars must be a mapping", messages)

    def test_yaml_and_basic_structure_errors_are_reported(self) -> None:
        """Core structure diagnostics should be stable before CLI integration."""
        cases = [
            ("profiles: [", "yaml"),
            ("- not-a-mapping\n", "cases.yml must be a mapping"),
            ("profiles: []\n", "`profiles` must be a mapping"),
            ("profiles: {}\n", "`profiles` must define at least one profile"),
            ("profiles:\n  sample: []\n", "profile must be a mapping"),
            ("profiles:\n  sample:\n    cases: {}\n", "profile cases must be a list"),
        ]

        for text, expected in cases:
            with self.subTest(expected=expected):
                path = self.write_cases_yaml(text)
                result = compile_cases_file(path)
                self.assertFalse(result.valid)
                if expected == "yaml":
                    self.assertEqual(result.diagnostics[0].location, "yaml")
                else:
                    self.assertIn(expected, result.diagnostics[0].message)

    def test_unknown_profile_is_reported(self) -> None:
        """Selecting a missing profile should return a compile diagnostic."""
        path = self.write_cases_yaml(
            """
profiles:
  sample:
    cases:
      - name: sample
        type: fixed
        content: ""
""".lstrip()
        )

        result = compile_cases_file(path, "hidden")

        self.assertFalse(result.valid)
        self.assertEqual(result.diagnostics[0].location, "profiles.hidden")
        self.assertIn("unknown profile: hidden", result.diagnostics[0].message)


if __name__ == "__main__":
    unittest.main()
