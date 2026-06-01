"""검증/팩 빌드 실패를 UI가 바로 렌더링할 수 있는 구조로 정리합니다."""
from __future__ import annotations

from typing import Any

STAGE_LABELS = {
    "cases": "cases.yml 검사",
    "tools": "도구 컴파일",
    "validation": "데이터 생성+검증",
    "solutions": "솔루션 기대 결과",
    "pack": "팩 생성",
}

STAGE_TARGETS = {
    "cases": "generator/cases.yml",
    "tools": "generator, validator, checker, 기준 정답",
    "validation": "generator/cases.yml, generator, validator",
    "solutions": "solutions/",
    "pack": "dist/packs",
}


def stage_label(stage: str | None) -> str:
    return STAGE_LABELS.get(stage or "", "검증")


def infer_failure_stage(message: str | None) -> str | None:
    text = str(message or "").lower()
    if not text:
        return None
    if "cases.yml" in text or "checking cases" in text or "compiling cases" in text:
        return "cases"
    if "tool" in text or "compile" in text or "compiling" in text:
        return "tools"
    if "generating" in text or "validating generated" in text or "data generated" in text:
        return "validation"
    if "solution" in text or "expected" in text or "verifying" in text:
        return "solutions"
    if "pack" in text or ".aljpack" in text:
        return "pack"
    return None


def compact_message(message: Any, limit: int = 700) -> str:
    text = str(message or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def exception_failure_payload(message: Any, stage: str | None = None) -> dict[str, Any]:
    stage_key = stage or infer_failure_stage(str(message)) or "unknown"
    return {
        "failureStage": stage_key,
        "failureStageLabel": stage_label(stage_key),
        "failureDetails": [
            {
                "type": stage_key,
                "label": stage_label(stage_key),
                "target": STAGE_TARGETS.get(stage_key, ""),
                "message": compact_message(message),
            }
        ],
    }


def solution_failure_details(verification: dict[str, Any]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for check in verification.get("checks", []) or []:
        if check.get("passed"):
            continue
        cases = check.get("cases") or []
        source = check.get("source") or check.get("path") or check.get("sourcePath") or ""
        details.append(
            {
                "type": "solution",
                "label": "솔루션 기대 결과",
                "source": source,
                "expectedStatus": check.get("expectedStatus") or "",
                "actualStatus": check.get("actualStatus") or "",
                "runId": check.get("runId") or "",
                "caseCount": len(cases),
                "message": compact_message(check.get("message") or ""),
            }
        )
    return details


def verification_failure_payload(verification: dict[str, Any]) -> dict[str, Any]:
    details = solution_failure_details(verification)
    if not details:
        return {}
    return {
        "failureStage": "solutions",
        "failureStageLabel": stage_label("solutions"),
        "failureDetails": details,
    }
