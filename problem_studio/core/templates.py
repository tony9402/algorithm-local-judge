"""템플릿 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError
from judge.core.paths import validate_safe_id
from judge.utils.fs import write_json
from problem_studio.core.workspace import problem_dir

GENERATOR_CPP = """#include "testlib.h"
#include <iostream>

int main(int argc, char* argv[]) {
    registerGen(argc, argv, 1);
    int n = opt<int>("n", 1);
    std::cout << n << "\\n";
    return 0;
}
"""

VALIDATOR_CPP = """#include "testlib.h"

int main(int argc, char* argv[]) {
    registerValidation(argc, argv);
    inf.readInt(1, 1000000, "n");
    inf.readEoln();
    inf.readEof();
    return 0;
}
"""

CHECKER_CPP = """#include "testlib.h"

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    int expected = ans.readInt();
    int actual = ouf.readInt();
    if (expected != actual) {
        quitf(_wa, "expected %d, got %d", expected, actual);
    }
    quitf(_ok, "accepted");
}
"""

SOLUTION_CPP = """#include <iostream>

int main() {
    int n;
    std::cin >> n;
    std::cout << n << "\\n";
    return 0;
}
"""

CASES_YML = """profiles:
  sample:
    cases:
      - name: sample-1
        type: fixed
        content: |
          1
  hidden:
    cases:
      - matrix:
          vars:
            n:
              range:
                from: 1
                to: 5
          item:
            name: "hidden-${n}"
            type: generator
            seed: "${n}"
            args:
              n: "${n}"
"""


def create_problem(
    workspace: Path,
    problem_id: str,
    title: str,
    folder: str = "",
    version: int = 1,
    default_profile: str = "hidden",
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """문제 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        workspace (Path): Problem Studio 또는 judge 데이터가 저장되는 작업 공간 루트입니다.
        problem_id (str): 문제를 찾고 결과를 저장할 때 사용하는 안전한 문제 ID입니다.
        title (str): 문제을 계산하거나 검증할 때 필요한 title 입력입니다.
        folder (str): 문제을 계산하거나 검증할 때 필요한 폴더 입력입니다.
        version (int): 문제을 계산하거나 검증할 때 필요한 version 입력입니다.
        default_profile (str): 문제을 계산하거나 검증할 때 필요한 default 프로필 입력입니다.
        limits (dict[str, Any] | None): 문제을 계산하거나 검증할 때 필요한 limits 입력입니다.

    Returns:
        dict[str, Any]: API 응답, 저장 파일, 또는 후속 서비스 호출에 전달할 문제 데이터입니다.
    """
    validate_safe_id("problem id", problem_id)
    target = problem_dir(workspace, problem_id)
    if target.exists():
        raise JudgeError(f"problem already exists: {problem_id}")
    limits = limits or {
        "compileTimeoutMs": 5000,
        "generationTimeoutMs": 5000,
        "solutionTimeoutMs": 2000,
        "userTimeoutMs": 2000,
        "userMemoryLimitMb": 2048,
    }
    files = {
        "generator/generator.cpp": GENERATOR_CPP,
        "generator/cases.yml": CASES_YML,
        "validator/validator.cpp": VALIDATOR_CPP,
        "checker/judge.cpp": CHECKER_CPP,
        "solutions/main_solution.ac.cpp": SOLUTION_CPP,
    }
    for relative, content in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    metadata = {
        "schemaVersion": 1,
        "problemId": problem_id,
        "title": title,
        "folder": folder.strip(),
        "version": version,
        "tools": {
            "generator": "generator/generator.cpp",
            "generatorConfig": "generator/cases.yml",
            "validator": "validator/validator.cpp",
            "checker": "checker/judge.cpp",
            "solution": "solutions/main_solution.ac.cpp",
        },
        "defaultProfile": default_profile,
        "limits": limits,
    }
    write_json(target / "problem.json", metadata)
    return {"problemId": problem_id, "path": str(target), "metadata": metadata}
