#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import itertools
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

EXPR_RE = re.compile(r"\$\{([^{}]+)\}")
MAX_NESTING_DEPTH = 2
SAFE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sha256_text(text: str) -> str:
    """Return the SHA-256 hex digest for generated input text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_scalar(value: str) -> Any:
    """Parse a small YAML-like scalar used by the fallback parser."""
    value = value.strip()
    if value in {"null", "None", "~"}:
        return None
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def load_with_fallback_parser(path: Path) -> dict[str, Any]:
    """Load the supported cases.yml subset without requiring PyYAML."""
    lines = path.read_text(encoding="utf-8").splitlines()
    data = {"profiles": {}}
    current_profile = None
    current_case = None
    in_args = False
    index = 0

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0 and stripped == "profiles:":
            index += 1
            continue
        if indent == 2 and stripped.endswith(":"):
            current_profile = stripped[:-1]
            data["profiles"][current_profile] = {"cases": []}
            current_case = None
            in_args = False
            index += 1
            continue
        if indent == 4 and stripped == "cases:":
            index += 1
            continue
        if indent == 6 and stripped.startswith("- "):
            current_case = {}
            data["profiles"][current_profile]["cases"].append(current_case)
            in_args = False
            remainder = stripped[2:]
            if remainder:
                key, value = remainder.split(":", 1)
                current_case[key.strip()] = parse_scalar(value)
            index += 1
            continue
        if indent == 8 and current_case is not None:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key == "args" and not value:
                current_case["args"] = {}
                in_args = True
                index += 1
                continue
            if value == "|":
                block = []
                index += 1
                while index < len(lines):
                    block_raw = lines[index]
                    block_indent = len(block_raw) - len(block_raw.lstrip(" "))
                    if block_raw.strip() and block_indent <= indent:
                        break
                    block.append(block_raw[10:] if len(block_raw) >= 10 else "")
                    index += 1
                current_case[key] = "\n".join(block) + "\n"
                continue
            current_case[key] = parse_scalar(value)
            in_args = False
            index += 1
            continue
        if indent == 10 and in_args and current_case is not None:
            key, value = stripped.split(":", 1)
            current_case["args"][key.strip()] = parse_scalar(value)
            index += 1
            continue

        raise ValueError(f"unsupported YAML structure at line {index + 1}: {raw}")

    return data


def load_config(path: Path) -> dict[str, Any]:
    """Load a generator configuration from YAML or the fallback parser."""
    try:
        import yaml

        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file)
    except ModuleNotFoundError:
        return load_with_fallback_parser(path)


def validate_variable_name(name: Any) -> None:
    """Validate a DSL variable name before adding it to context."""
    if not isinstance(name, str) or not SAFE_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid variable name: {name}")
    if name.startswith("_"):
        raise ValueError(f"variable name must not start with underscore: {name}")


def resolve_attribute(value: Any, attr: str) -> Any:
    """Resolve safe mapping field access in DSL expressions."""
    if attr.startswith("_"):
        raise ValueError(f"private attribute access is not allowed: {attr}")
    if isinstance(value, dict):
        if attr not in value:
            raise ValueError(f"unknown field: {attr}")
        return value[attr]
    raise ValueError(f"field access is only allowed on mappings: {attr}")


def eval_ast(node: ast.AST, context: Mapping[str, Any]) -> Any:
    """Evaluate the restricted expression AST used by case templates."""
    if isinstance(node, ast.Expression):
        return eval_ast(node.body, context)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, str, bool)):
            return node.value
        raise ValueError(f"unsupported literal: {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id not in context:
            raise ValueError(f"unknown variable: {node.id}")
        return context[node.id]
    if isinstance(node, ast.Attribute):
        return resolve_attribute(eval_ast(node.value, context), node.attr)
    if isinstance(node, ast.UnaryOp):
        operand = eval_ast(node.operand, context)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError("unsupported unary operator")
    if isinstance(node, ast.BinOp):
        left = eval_ast(node.left, context)
        right = eval_ast(node.right, context)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        raise ValueError("unsupported binary operator")
    if isinstance(node, ast.BoolOp):
        values = [bool(eval_ast(value, context)) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        raise ValueError("unsupported boolean operator")
    if isinstance(node, ast.Compare):
        left = eval_ast(node.left, context)
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = eval_ast(comparator, context)
            if isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            elif isinstance(op, ast.Gt):
                ok = left > right
            elif isinstance(op, ast.GtE):
                ok = left >= right
            elif isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            else:
                raise ValueError("unsupported comparison operator")
            if not ok:
                return False
            left = right
        return True
    raise ValueError(f"unsupported expression: {ast.dump(node, include_attributes=False)}")


def split_format_expression(expr: str) -> tuple[str, str | None]:
    """Split `${expr:format}` while leaving normal colon expressions intact."""
    if ":" not in expr:
        return expr.strip(), None
    expression, fmt = expr.rsplit(":", 1)
    if not fmt or any(char.isspace() for char in fmt):
        return expr.strip(), None
    return expression.strip(), fmt.strip()


def safe_eval(expr: str, context: Mapping[str, Any]) -> Any:
    """Evaluate a safe expression against the current DSL context."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid expression: {expr}") from exc
    return eval_ast(tree, context)


def render_expression(expr: str, context: Mapping[str, Any]) -> Any:
    """Render one `${...}` expression, applying an optional format spec."""
    expression, fmt = split_format_expression(expr)
    value = safe_eval(expression, context)
    if fmt is not None:
        return format(value, fmt)
    return value


def render_string(value: str, context: Mapping[str, Any]) -> Any:
    """Render all `${...}` expressions inside a string value."""
    full_match = EXPR_RE.fullmatch(value.strip())
    if full_match and value.strip() == value:
        return render_expression(full_match.group(1), context)

    def replace(match: re.Match[str]) -> str:
        """Render one embedded expression as text for substitution."""
        rendered = render_expression(match.group(1), context)
        return str(rendered)

    return EXPR_RE.sub(replace, value)


def render_value(value: Any, context: Mapping[str, Any]) -> Any:
    """Recursively render expressions in scalar, list, and mapping values."""
    if isinstance(value, str):
        return render_string(value, context)
    if isinstance(value, list):
        return [render_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: render_value(item, context) for key, item in value.items()}
    return value


def repeat_values(block: Mapping[str, Any], context: Mapping[str, Any]) -> list[Any]:
    """Return the iteration values for a repeat block."""
    if "in" in block:
        values = render_value(block["in"], context)
        if not isinstance(values, list):
            raise ValueError("repeat.in must be a list")
        return values

    if "from" not in block or "to" not in block:
        raise ValueError("repeat requires either in or from/to")
    start = render_value(block["from"], context)
    stop = render_value(block["to"], context)
    step = render_value(block.get("step", 1), context)
    if not all(isinstance(value, int) for value in [start, stop, step]):
        raise ValueError("repeat from/to/step must be integers")
    if step == 0:
        raise ValueError("repeat step must not be zero")
    if step > 0:
        return list(range(start, stop + 1, step))
    return list(range(start, stop - 1, step))


def repeat_items(block: Mapping[str, Any]) -> list[Any]:
    """Return the item list nested under a repeat block."""
    if "item" in block and "items" in block:
        raise ValueError("repeat must not define both item and items")
    if "item" in block:
        return [block["item"]]
    if "items" in block:
        items = block["items"]
        if not isinstance(items, list):
            raise ValueError("repeat.items must be a list")
        return items
    raise ValueError("repeat requires item or items")


def expand_repeat(
    block: Mapping[str, Any], context: Mapping[str, Any], depth: int
) -> list[dict[str, Any]]:
    """Expand a repeat block into concrete case definitions."""
    if depth >= MAX_NESTING_DEPTH:
        raise ValueError(f"repeat nesting is limited to {MAX_NESTING_DEPTH} levels")
    var = block.get("var")
    validate_variable_name(var)
    if var in context:
        raise ValueError(f"nested repeat shadows variable: {var}")

    expanded = []
    for value in repeat_values(block, context):
        next_context = {**context, var: value}
        expanded.extend(expand_cases(repeat_items(block), next_context, depth + 1))
    return expanded


def matrix_items(block: Mapping[str, Any]) -> list[Any]:
    """Return the item list nested under a matrix block."""
    if "item" in block and "items" in block:
        raise ValueError("matrix must not define both item and items")
    if "item" in block:
        return [block["item"]]
    if "items" in block:
        items = block["items"]
        if not isinstance(items, list):
            raise ValueError("matrix.items must be a list")
        return items
    raise ValueError("matrix requires item or items")


def matrix_variable_values(name: str, candidates: Any, context: Mapping[str, Any]) -> list[Any]:
    """Return values for one matrix variable from a list or range block."""
    if isinstance(candidates, list):
        return [render_value(candidate, context) for candidate in candidates]
    if isinstance(candidates, dict):
        if set(candidates) != {"range"}:
            raise ValueError(f"matrix variable mapping supports only range: {name}")
        range_config = candidates["range"]
        if not isinstance(range_config, Mapping):
            raise ValueError(f"matrix variable range must be a mapping: {name}")
        return repeat_values(range_config, context)
    raise ValueError(f"matrix variable must be a list or range mapping: {name}")


def expand_matrix(
    block: Mapping[str, Any], context: Mapping[str, Any], depth: int
) -> list[dict[str, Any]]:
    """Expand a matrix block into concrete case definitions."""
    if depth >= MAX_NESTING_DEPTH:
        raise ValueError(f"matrix nesting is limited to {MAX_NESTING_DEPTH} levels")
    vars_config = block.get("vars", {})
    if not isinstance(vars_config, dict) or not vars_config:
        raise ValueError("matrix.vars must be a non-empty mapping")

    names = []
    values = []
    for name, candidates in vars_config.items():
        validate_variable_name(name)
        if name in context:
            raise ValueError(f"matrix shadows variable: {name}")
        names.append(name)
        values.append(matrix_variable_values(name, candidates, context))

    expanded = []
    for combination in itertools.product(*values):
        next_context = {**context, **dict(zip(names, combination, strict=True))}
        where = block.get("where")
        if where is not None and not bool(safe_eval(str(where), next_context)):
            continue
        expanded.extend(expand_cases(matrix_items(block), next_context, depth + 1))
    return expanded


def expand_cases(
    cases_config: Sequence[Any],
    context: Mapping[str, Any] | None = None,
    depth: int = 0,
) -> list[dict[str, Any]]:
    """Expand fixed, repeat, and matrix case entries into concrete cases."""
    context = context or {}
    expanded = []
    for case in cases_config:
        if not isinstance(case, dict):
            raise ValueError("case must be a mapping")
        if "repeat" in case:
            expanded.extend(expand_repeat(case["repeat"], context, depth))
        elif "matrix" in case:
            expanded.extend(expand_matrix(case["matrix"], context, depth))
        else:
            expanded.append(render_value(copy.deepcopy(case), context))
    return expanded


def run_generator(generator: Path, case: Mapping[str, Any]) -> str:
    """Run a compiled testlib generator for one case definition."""
    seed = case.get("seed")
    if seed is None:
        raise ValueError(f"generator case requires seed: {case.get('name')}")
    args = case.get("args", {})
    command = [str(generator), str(seed)]
    for key, value in args.items():
        command.append(f"--{key}={value}")
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        detail = (
            f"generator failed for case {case.get('name')} "
            f"(runtime error, exit code {result.returncode})"
        )
        if result.stderr.strip():
            detail = f"{detail}: {result.stderr.strip()}"
        raise RuntimeError(detail)
    return result.stdout


def render_template(case: Mapping[str, Any]) -> str:
    """Render a Python format template case."""
    template = case.get("template")
    if template is None:
        raise ValueError(f"template case requires template: {case.get('name')}")
    variables = case.get("vars", {})
    return template.format(**variables)


def render_case(generator: Path, case: Mapping[str, Any]) -> str:
    """Render one case to input text according to its case type."""
    case_type = case.get("type")
    if case_type == "fixed":
        return case.get("content", "")
    if case_type == "template":
        return render_template(case)
    if case_type == "generator":
        return run_generator(generator, case)
    raise ValueError(f"unknown case type: {case_type}")


def write_cases(
    config: Mapping[str, Any], generator: Path, out_dir: Path, profile: str
) -> list[dict[str, Any]]:
    """Write all expanded input cases for a profile and return summaries."""
    profiles = config.get("profiles", {})
    if profile not in profiles:
        raise ValueError(f"unknown profile: {profile}")
    cases_config = expand_cases(profiles[profile].get("cases", []))
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = []
    case_names = set()
    for index, case in enumerate(cases_config, start=1):
        case_id = f"{index:03d}"
        case_name = case.get("name", case_id)
        if case_name in case_names:
            raise ValueError(f"duplicate case name: {case_name}")
        case_names.add(case_name)
        content = render_case(generator, case)
        path = out_dir / f"{case_id}.in"
        path.write_text(content, encoding="utf-8")
        cases.append(
            {
                "id": case_id,
                "name": case_name,
                "seed": case.get("seed"),
                "method": case.get("type"),
                "input": path.name,
                "inputHash": sha256_text(content),
            }
        )
    return cases


def generate_cases(
    config_path: Path,
    generator: Path,
    out_dir: Path,
    profile: str,
) -> dict[str, Any]:
    """Generate input files for a profile and return a structured summary."""
    if not generator.exists():
        raise FileNotFoundError(f"generator not found: {generator}")
    if not config_path.exists():
        raise FileNotFoundError(f"generator config not found: {config_path}")
    config = load_config(config_path)
    cases = write_cases(config, generator, out_dir, profile)
    return {"profile": profile, "cases": cases}


def parse_args() -> argparse.Namespace:
    """Parse the common generator script CLI arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--generator", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--profile", required=True)
    return parser.parse_args()


def main() -> None:
    """Generate input files and emit a JSON summary to stdout."""
    args = parse_args()
    try:
        summary = generate_cases(
            Path(args.config),
            Path(args.generator),
            Path(args.out),
            args.profile,
        )
    except Exception as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
