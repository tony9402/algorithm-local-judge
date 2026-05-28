#!/usr/bin/env python3

"""cases.yml에 정의된 고정 입력, 템플릿, 생성기 기반 케이스를 확장해 채점 입력 파일과 매니페스트를 만드는 유틸리티입니다."""
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
FULL_PROFILE = "full"


def sha256_text(text: str) -> str:
    """생성된 입력 문자열을 UTF-8 바이트로 인코딩해 SHA-256 해시를 계산합니다.

    Args:
        text (str): 입력 파일에 기록된 원문 문자열입니다.

    Returns:
        str: 입력 문자열의 SHA-256 해시를 16진수로 표현한 값입니다.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_scalar(value: str) -> Any:
    """fallback YAML 파서가 읽은 스칼라 문자열을 null, bool, int, 문자열 값으로 변환합니다.

    Args:
        value (str): cases.yml에서 읽은 스칼라 표현 문자열입니다.

    Returns:
        Any: DSL 평가와 케이스 렌더링에 사용할 Python 값입니다.
    """
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
    """PyYAML이 없는 환경에서 지원 가능한 cases.yml 하위 구조만 직접 읽습니다. 프로필, 케이스 목록, args 맵, 블록 문자열을 처리하고 지원하지 않는 구조는 명시적으로 거부합니다.

    Args:
        path (Path): 읽을 cases.yml 파일 경로입니다.

    Returns:
        dict[str, Any]: `profiles` 키를 포함한 생성 설정 사전입니다.
    """
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
    """YAML 설정을 로드하되 PyYAML이 설치되지 않은 배포 환경에서는 내장 fallback 파서를 사용합니다.

    Args:
        path (Path): 생성 DSL 설정 파일 경로입니다.

    Returns:
        dict[str, Any]: 케이스 생성에 사용할 설정 데이터입니다.
    """
    try:
        import yaml

        with path.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file)
    except ModuleNotFoundError:
        return load_with_fallback_parser(path)


def validate_variable_name(name: Any) -> None:
    """반복과 행렬 DSL에서 컨텍스트에 추가할 변수명이 안전한 Python 식별자 형태인지 검증합니다.

    Args:
        name (Any): DSL의 `var` 또는 `vars` 항목에서 읽은 변수명 후보입니다.
    """
    if not isinstance(name, str) or not SAFE_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid variable name: {name}")
    if name.startswith("_"):
        raise ValueError(f"variable name must not start with underscore: {name}")


def resolve_attribute(value: Any, attr: str) -> Any:
    """제한된 표현식에서 `item.field` 형태의 매핑 필드 접근만 허용하고, 비공개 이름이나 알 수 없는 필드는 거부합니다.

    Args:
        value (Any): 필드 접근 대상이 되는 평가 결과입니다.
        attr (str): 표현식에서 요청한 필드 이름입니다.

    Returns:
        Any: 매핑에서 조회한 필드 값입니다.
    """
    if attr.startswith("_"):
        raise ValueError(f"private attribute access is not allowed: {attr}")
    if isinstance(value, dict):
        if attr not in value:
            raise ValueError(f"unknown field: {attr}")
        return value[attr]
    raise ValueError(f"field access is only allowed on mappings: {attr}")


def eval_ast(node: ast.AST, context: Mapping[str, Any]) -> Any:
    """생성 DSL 표현식에 허용된 AST 노드만 재귀적으로 평가합니다. 리터럴, 변수, 매핑 필드, 산술, 비교, 불리언 연산만 허용해 임의 코드 실행을 막습니다.

    Args:
        node (ast.AST): `ast.parse(..., mode="eval")`로 만든 표현식 AST 노드입니다.
        context (Mapping[str, Any]): 반복과 행렬 확장에서 현재 사용할 변수 값 사전입니다.

    Returns:
        Any: 제한된 표현식을 평가한 결과 값입니다.
    """
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
    """`${expr:format}` 표현식에서 실제 평가식과 선택적 포맷 지정자를 분리합니다. 공백이 있는 콜론 표현식은 일반 표현식으로 유지합니다.

    Args:
        expr (str): `${...}` 안에서 추출한 표현식 문자열입니다.

    Returns:
        tuple[str, str | None]: 평가할 표현식과 포맷 지정자입니다. 포맷이 없으면 두 번째 값은 `None`입니다.
    """
    if ":" not in expr:
        return expr.strip(), None
    expression, fmt = expr.rsplit(":", 1)
    if not fmt or any(char.isspace() for char in fmt):
        return expr.strip(), None
    return expression.strip(), fmt.strip()


def safe_eval(expr: str, context: Mapping[str, Any]) -> Any:
    """DSL 템플릿 표현식을 AST로 파싱한 뒤 허용된 연산만 평가합니다.

    Args:
        expr (str): `${...}` 안에 작성된 표현식 문자열입니다.
        context (Mapping[str, Any]): 표현식에서 참조할 수 있는 현재 변수 값 사전입니다.

    Returns:
        Any: 제한된 표현식 평가 결과입니다.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid expression: {expr}") from exc
    return eval_ast(tree, context)


def render_expression(expr: str, context: Mapping[str, Any]) -> Any:
    """하나의 `${...}` 표현식을 평가하고, 포맷 지정자가 있으면 Python 포맷 규칙을 적용합니다.

    Args:
        expr (str): 렌더링할 DSL 표현식 문자열입니다.
        context (Mapping[str, Any]): 표현식 평가에 사용할 현재 변수 값 사전입니다.

    Returns:
        Any: 표현식 평가 결과 또는 포맷된 문자열입니다.
    """
    expression, fmt = split_format_expression(expr)
    value = safe_eval(expression, context)
    if fmt is not None:
        return format(value, fmt)
    return value


def render_string(value: str, context: Mapping[str, Any]) -> Any:
    """문자열 안의 `${...}` 표현식을 모두 렌더링합니다. 문자열 전체가 표현식 하나인 경우에는 원래 타입을 유지합니다.

    Args:
        value (str): 렌더링할 템플릿 문자열입니다.
        context (Mapping[str, Any]): 표현식 평가에 사용할 현재 변수 값 사전입니다.

    Returns:
        Any: 렌더링된 문자열 또는 전체 표현식의 원래 타입 값입니다.
    """
    full_match = EXPR_RE.fullmatch(value.strip())
    if full_match and value.strip() == value:
        return render_expression(full_match.group(1), context)

    def replace(match: re.Match[str]) -> str:
        """정규식으로 찾은 템플릿 표현식 하나를 평가해 문자열 치환값으로 변환합니다.

        Args:
            match (re.Match[str]): `${...}` 표현식 하나에 대한 정규식 매치 객체입니다.

        Returns:
            str: 템플릿 문자열에 삽입할 표현식 평가 결과입니다.
        """
        rendered = render_expression(match.group(1), context)
        return str(rendered)

    return EXPR_RE.sub(replace, value)


def render_value(value: Any, context: Mapping[str, Any]) -> Any:
    """케이스 설정 값 내부의 문자열, 리스트, 사전을 순회하며 포함된 DSL 표현식을 렌더링합니다.

    Args:
        value (Any): 렌더링할 케이스 설정 값입니다.
        context (Mapping[str, Any]): 표현식 평가에 사용할 현재 변수 값 사전입니다.

    Returns:
        Any: 입력 구조를 유지하면서 표현식이 치환된 값입니다.
    """
    if isinstance(value, str):
        return render_string(value, context)
    if isinstance(value, list):
        return [render_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: render_value(item, context) for key, item in value.items()}
    return value


def repeat_values(block: Mapping[str, Any], context: Mapping[str, Any]) -> list[Any]:
    """repeat 블록의 `in` 목록 또는 `from`/`to`/`step` 범위를 실제 반복 값 목록으로 확장합니다.

    Args:
        block (Mapping[str, Any]): `var`, `in` 또는 `from`/`to`/`step`을 포함한 repeat 설정입니다.
        context (Mapping[str, Any]): 반복 범위 표현식을 렌더링할 현재 변수 값 사전입니다.

    Returns:
        list[Any]: repeat 블록이 순회할 값 목록입니다.
    """
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
    """repeat 블록 안에서 반복 대상이 되는 단일 케이스 또는 케이스 목록을 정규화합니다.

    Args:
        block (Mapping[str, Any]): `item` 또는 `items`를 포함한 repeat 설정입니다.

    Returns:
        list[Any]: 반복 확장에 사용할 케이스 설정 목록입니다.
    """
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
    """repeat 블록을 현재 컨텍스트에 변수로 바인딩하며 하위 케이스 목록으로 확장합니다. 중첩 깊이와 변수 섀도잉을 제한합니다.

    Args:
        block (Mapping[str, Any]): 확장할 repeat 설정입니다.
        context (Mapping[str, Any]): 상위 반복 또는 행렬에서 전달된 변수 값 사전입니다.
        depth (int): 현재 repeat/matrix 중첩 깊이입니다.

    Returns:
        list[dict[str, Any]]: 렌더링 준비가 끝난 케이스 설정 목록입니다.
    """
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
    """matrix 블록 안에서 조합마다 복제할 단일 케이스 또는 케이스 목록을 정규화합니다.

    Args:
        block (Mapping[str, Any]): `vars`와 `item` 또는 `items`를 포함한 matrix 설정입니다.

    Returns:
        list[Any]: 행렬 조합마다 확장할 케이스 설정 목록입니다.
    """
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
    """matrix 변수 하나의 후보 값을 목록 또는 range 매핑에서 계산합니다.

    Args:
        name (str): 후보 값을 계산할 matrix 변수명입니다.
        candidates (Any): 변수 후보 목록 또는 `range` 설정 매핑입니다.
        context (Mapping[str, Any]): 후보 값 표현식을 렌더링할 현재 변수 값 사전입니다.

    Returns:
        list[Any]: 해당 matrix 변수가 가질 수 있는 값 목록입니다.
    """
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
    """matrix 블록의 변수 후보 곱집합을 순회하며 where 조건을 통과한 조합만 하위 케이스로 확장합니다.

    Args:
        block (Mapping[str, Any]): `vars`, 선택적 `where`, `item` 또는 `items`를 포함한 matrix 설정입니다.
        context (Mapping[str, Any]): 상위 반복 또는 행렬에서 전달된 변수 값 사전입니다.
        depth (int): 현재 repeat/matrix 중첩 깊이입니다.

    Returns:
        list[dict[str, Any]]: 모든 허용 조합이 확장된 케이스 설정 목록입니다.
    """
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
    """cases.yml의 케이스 목록을 순회하며 repeat와 matrix DSL을 실제 케이스 목록으로 펼칩니다.

    Args:
        cases_config (Sequence[Any]): 프로필에 선언된 원본 케이스 설정 목록입니다.
        context (Mapping[str, Any] | None): 상위 DSL 블록에서 전달된 변수 값 사전입니다.
        depth (int): 현재 repeat/matrix 중첩 깊이입니다.

    Returns:
        list[dict[str, Any]]: 생성 방식과 이름이 확정된 케이스 설정 목록입니다.
    """
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
    """외부 생성기 실행 파일에 seed와 args를 전달해 한 케이스의 입력 텍스트를 생성합니다.

    Args:
        generator (Path): 컴파일된 테스트 데이터 생성기 실행 파일 경로입니다.
        case (Mapping[str, Any]): `seed`, 선택적 `args`, `name`을 포함한 generator 케이스 설정입니다.

    Returns:
        str: 생성기가 표준 출력으로 기록한 입력 데이터입니다.
    """
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
    """template 케이스의 문자열에 `vars` 값을 적용해 입력 텍스트를 만듭니다.

    Args:
        case (Mapping[str, Any]): `template`과 선택적 `vars`를 포함한 template 케이스 설정입니다.

    Returns:
        str: 포맷 적용이 끝난 입력 데이터입니다.
    """
    template = case.get("template")
    if template is None:
        raise ValueError(f"template case requires template: {case.get('name')}")
    variables = case.get("vars", {})
    return template.format(**variables)


def render_case(generator: Path, case: Mapping[str, Any]) -> str:
    """케이스 타입에 따라 고정 입력, 템플릿 입력, 생성기 입력 중 하나를 렌더링합니다.

    Args:
        generator (Path): generator 타입 케이스가 사용할 실행 파일 경로입니다.
        case (Mapping[str, Any]): 렌더링할 케이스 설정입니다.

    Returns:
        str: `.in` 파일에 기록할 입력 데이터입니다.
    """
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
    """선택한 프로필의 케이스를 확장하고 각 입력 파일과 매니페스트 항목을 출력 디렉터리에 기록합니다.

    Args:
        config (Mapping[str, Any]): `profiles`를 포함한 전체 생성 설정입니다.
        generator (Path): generator 타입 케이스가 사용할 실행 파일 경로입니다.
        out_dir (Path): 생성된 `.in` 파일을 기록할 출력 디렉터리입니다.
        profile (str): 생성할 프로필 이름입니다. `full` 합성 프로필도 처리합니다.

    Returns:
        list[dict[str, Any]]: 생성된 각 케이스의 식별자, 이름, seed, 입력 파일명, 해시 정보입니다.
    """
    profiles = config.get("profiles", {})
    if profile == FULL_PROFILE and profile not in profiles:
        cases_source = []
        for profile_config in profiles.values():
            cases_source.extend(profile_config.get("cases", []))
    elif profile in profiles:
        cases_source = profiles[profile].get("cases", [])
    else:
        raise ValueError(f"unknown profile: {profile}")
    cases_config = expand_cases(cases_source)
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
    """설정 파일과 생성기를 검증한 뒤 요청한 프로필의 입력 파일을 생성하고 요약 정보를 반환합니다.

    Args:
        config_path (Path): cases.yml 생성 설정 파일 경로입니다.
        generator (Path): generator 타입 케이스가 사용할 실행 파일 경로입니다.
        out_dir (Path): 생성된 입력 파일을 기록할 출력 디렉터리입니다.
        profile (str): 생성할 프로필 이름입니다.

    Returns:
        dict[str, Any]: 생성한 프로필 이름과 케이스 매니페스트 목록입니다.
    """
    if not generator.exists():
        raise FileNotFoundError(f"generator not found: {generator}")
    if not config_path.exists():
        raise FileNotFoundError(f"generator config not found: {config_path}")
    config = load_config(config_path)
    cases = write_cases(config, generator, out_dir, profile)
    return {"profile": profile, "cases": cases}


def parse_args() -> argparse.Namespace:
    """입력 생성 명령에서 사용할 설정 파일, 생성기, 출력 디렉터리, 프로필 인자를 파싱합니다.

    Returns:
        argparse.Namespace: `config`, `generator`, `out`, `profile` 값을 담은 명령줄 인자 네임스페이스입니다.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--generator", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--profile", required=True)
    return parser.parse_args()


def main() -> None:
    """명령줄 인자를 바탕으로 케이스를 생성하고, 성공 시 생성 요약 JSON을 표준 출력에 기록합니다."""
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
