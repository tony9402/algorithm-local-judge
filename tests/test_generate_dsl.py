from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from commons.generate import expand_cases, write_cases


class GenerateDslTest(unittest.TestCase):
    """Unit tests for the generator YAML expansion DSL."""

    def test_repeat_range_expands_and_renders_values(self) -> None:
        """Repeat ranges should expand and preserve numeric rendered values."""
        cases = expand_cases(
            [
                {
                    "repeat": {
                        "var": "i",
                        "from": 1,
                        "to": 3,
                        "item": {
                            "name": "case-${i:02d}",
                            "type": "generator",
                            "seed": "${4000 + i}",
                            "args": {
                                "minN": "${i}",
                                "maxN": "${i}",
                                "minM": 1,
                                "maxM": "${i}",
                            },
                        },
                    }
                }
            ]
        )
        self.assertEqual([case["name"] for case in cases], ["case-01", "case-02", "case-03"])
        self.assertEqual([case["seed"] for case in cases], [4001, 4002, 4003])
        self.assertEqual(cases[2]["args"]["maxN"], 3)
        self.assertIsInstance(cases[2]["args"]["maxN"], int)

    def test_fixed_content_preserves_newline(self) -> None:
        """Fixed cases should keep trailing newlines after expression rendering."""
        cases = expand_cases(
            [
                {
                    "repeat": {
                        "var": "i",
                        "from": 1,
                        "to": 1,
                        "item": {
                            "name": "fixed-${i}",
                            "type": "fixed",
                            "content": "${i} 1\n",
                        },
                    }
                }
            ]
        )
        self.assertEqual(cases[0]["content"], "1 1\n")

    def test_nested_repeat_can_use_parent_context(self) -> None:
        """Nested repeat blocks should read variables from parent context."""
        cases = expand_cases(
            [
                {
                    "repeat": {
                        "var": "n",
                        "from": 1,
                        "to": 3,
                        "items": [
                            {
                                "repeat": {
                                    "var": "m",
                                    "from": 1,
                                    "to": "${n}",
                                    "item": {
                                        "name": "n-${n}-m-${m}",
                                        "type": "fixed",
                                        "content": "${n} ${m}\n",
                                    },
                                }
                            }
                        ],
                    }
                }
            ]
        )
        self.assertEqual(
            [case["name"] for case in cases],
            ["n-1-m-1", "n-2-m-1", "n-2-m-2", "n-3-m-1", "n-3-m-2", "n-3-m-3"],
        )

    def test_matrix_expands_in_stable_order_and_filters(self) -> None:
        """Matrix blocks should expand in stable order and honor where filters."""
        cases = expand_cases(
            [
                {
                    "matrix": {
                        "vars": {
                            "n": [1, 2],
                            "m": [1, 2],
                        },
                        "where": "m <= n",
                        "item": {
                            "name": "n-${n}-m-${m}",
                            "type": "generator",
                            "seed": "${1000 + n * 10 + m}",
                            "args": {
                                "minN": "${n}",
                                "maxN": "${n}",
                                "minM": "${m}",
                                "maxM": "${m}",
                            },
                        },
                    }
                }
            ]
        )
        self.assertEqual([case["name"] for case in cases], ["n-1-m-1", "n-2-m-1", "n-2-m-2"])
        self.assertEqual([case["seed"] for case in cases], [1011, 1021, 1022])

    def test_matrix_range_variables_expand_inclusively(self) -> None:
        """Matrix variables may use repeat-style inclusive range blocks."""
        cases = expand_cases(
            [
                {
                    "matrix": {
                        "vars": {
                            "n": {
                                "range": {
                                    "from": 1,
                                    "to": 3,
                                }
                            },
                            "m": {
                                "range": {
                                    "from": 2,
                                    "to": 6,
                                    "step": 2,
                                }
                            },
                        },
                        "where": "m <= n * 2",
                        "item": {
                            "name": "n-${n}-m-${m}",
                            "type": "generator",
                            "seed": "${2000 + n * 10 + m}",
                            "args": {
                                "minN": "${n}",
                                "maxN": "${n}",
                                "minM": "${m}",
                                "maxM": "${m}",
                            },
                        },
                    }
                }
            ]
        )
        self.assertEqual(
            [case["name"] for case in cases],
            ["n-1-m-2", "n-2-m-2", "n-2-m-4", "n-3-m-2", "n-3-m-4", "n-3-m-6"],
        )
        self.assertEqual([case["seed"] for case in cases], [2012, 2022, 2024, 2032, 2034, 2036])

    def test_unsafe_expression_is_rejected(self) -> None:
        """Expression rendering should reject unsafe Python constructs."""
        with self.assertRaises(ValueError):
            expand_cases(
                [
                    {
                        "repeat": {
                            "var": "i",
                            "from": 1,
                            "to": 1,
                            "item": {
                                "name": "${__import__('os').system('true')}",
                                "type": "fixed",
                                "content": "1 1\n",
                            },
                        }
                    }
                ]
            )

    def test_duplicate_case_name_is_left_to_writer_layer(self) -> None:
        """Expansion should not deduplicate names before the writer layer."""
        cases = expand_cases(
            [
                {"name": "same", "type": "fixed", "content": "1 1\n"},
                {"name": "same", "type": "fixed", "content": "1 1\n"},
            ]
        )
        self.assertEqual([case["name"] for case in cases], ["same", "same"])

    def test_synthetic_full_profile_writes_all_declared_profile_cases(self) -> None:
        """`full` should write sample and hidden cases when no explicit full profile exists."""
        config = {
            "profiles": {
                "sample": {
                    "cases": [{"name": "sample", "type": "fixed", "content": "1 1\n"}],
                },
                "hidden": {
                    "cases": [{"name": "hidden", "type": "fixed", "content": "2 2\n"}],
                },
            }
        }
        with tempfile.TemporaryDirectory(prefix="alj-generate-full-") as tmp:
            out_dir = Path(tmp) / "cases"

            cases = write_cases(config, Path(tmp) / "unused-generator", out_dir, "full")

        self.assertEqual([case["name"] for case in cases], ["sample", "hidden"])
        self.assertEqual([case["input"] for case in cases], ["001.in", "002.in"])


if __name__ == "__main__":
    unittest.main()
