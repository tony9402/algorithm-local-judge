"""cases.yml 확장 규칙, 스키마 검증, 진단 메시지 계약을 단위 수준에서 검증하는 테스트 모듈입니다."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from judge.core.cases_compile import compile_cases_file, format_compile_result


class CasesCompileTest(unittest.TestCase):
    """케이스 컴파일 테스트 시나리오를 묶어 API, 명령줄, 화면 계약이 회귀하지 않는지 검증하는 테스트 케이스입니다."""

    def write_cases_yaml(self, text: str) -> Path:
        """케이스 YAML 테스트 입력을 파일 시스템에 기록해 실제 파서와 실행기가 같은 경로를 읽도록 합니다.

        Args:
            text (str): 파일에 기록하거나 브라우저에서 기다릴 텍스트입니다.

        Returns:
            Path: 작성된 cases.yml 파일 경로입니다.
        """
        directory = tempfile.TemporaryDirectory(prefix="alj-cases-compile-")
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "cases.yml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_compiles_fixed_repeat_and_matrix_range(self) -> None:
        """컴파일 고정 반복 및 행렬 범위 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """행렬 널 보고 들여쓰기 힌트 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """알 수 없는 표현식 변수 진단 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """스키마 오류 수집 이후 확장 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """중복 케이스 이름 보고 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """불리언 시드 않도록 취급 정수 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """고정 및 템플릿 스칼라 타입 검증 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """널 인자 변수 및 누락 타입 보고 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """YAML 및 기본 구조 오류 보고 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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
        """알 수 없는 프로필 보고 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
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

    def test_synthetic_full_profile_compiles_all_declared_profiles(self) -> None:
        """합성 전체 프로필 컴파일 전체 선언된 프로필 시나리오에서 공개 동작, 오류 처리, 사용자 표시 계약이 유지되는지 검증합니다."""
        path = self.write_cases_yaml(
            """
profiles:
  sample:
    cases:
      - name: sample
        type: fixed
        content: ""
  hidden:
    cases:
      - name: hidden
        type: fixed
        content: ""
""".lstrip()
        )

        result = compile_cases_file(path, "full")

        self.assertTrue(result.valid, format_compile_result(result))
        self.assertEqual([profile.name for profile in result.profiles], ["sample", "hidden"])
        self.assertEqual(sum(len(profile.cases) for profile in result.profiles), 2)


if __name__ == "__main__":
    unittest.main()
