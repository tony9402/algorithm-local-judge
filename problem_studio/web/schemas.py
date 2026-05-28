"""schemas 웹 백엔드 구성과 응답 데이터 조립을 담당합니다.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkspaceOpenRequest(BaseModel):
    """API에서 주고받는 작업 공간 open 요청 필드를 검증하는 스키마입니다.
    """

    path: str = Field(min_length=1)


class GitCloneRequest(BaseModel):
    """API에서 주고받는 Git clone 요청 필드를 검증하는 스키마입니다.
    """

    url: str = Field(min_length=1)
    path: str = Field(min_length=1)
    branch: str | None = None


class GitCommitRequest(BaseModel):
    """API에서 주고받는 Git commit 요청 필드를 검증하는 스키마입니다.
    """

    message: str = Field(min_length=1)
    files: list[str] | None = None


class RepositorySelectRequest(BaseModel):
    """API에서 주고받는 저장소 select 요청 필드를 검증하는 스키마입니다.
    """

    repo_name: str = Field(min_length=1)


class RepositoryCloneRequest(BaseModel):
    """API에서 주고받는 저장소 clone 요청 필드를 검증하는 스키마입니다.
    """

    url: str = Field(min_length=1)
    branch: str | None = None
    repo_name: str | None = None


class RepositoryRegisterRequest(BaseModel):
    """API에서 주고받는 저장소 register 요청 필드를 검증하는 스키마입니다.
    """

    repo_name: str = Field(min_length=1)


class ProblemCreateRequest(BaseModel):
    """API에서 주고받는 문제 create 요청 필드를 검증하는 스키마입니다.
    """

    problem_id: str = Field(min_length=1)
    title: str = "Untitled Problem"
    folder: str = ""
    version: int = 1
    default_profile: str = "hidden"
    limits: dict[str, Any] | None = None


class ProblemDeleteRequest(BaseModel):
    """API에서 주고받는 문제 delete 요청 필드를 검증하는 스키마입니다.
    """

    confirm_phrase: str = Field(min_length=1)


class ProblemRenameRequest(BaseModel):
    """API에서 주고받는 문제 rename 요청 필드를 검증하는 스키마입니다.
    """

    problem_id: str = Field(min_length=1)


class MetadataPatchRequest(BaseModel):
    """API에서 주고받는 메타데이터 patch 요청 필드를 검증하는 스키마입니다.
    """

    metadata: dict[str, Any]


class FileWriteRequest(BaseModel):
    """API에서 주고받는 파일 쓰기 요청 필드를 검증하는 스키마입니다.
    """

    content: str


class CasesCompileRequest(BaseModel):
    """API에서 주고받는 케이스 컴파일 요청 필드를 검증하는 스키마입니다.
    """

    profile: str | None = None


class GenerateRequest(BaseModel):
    """API에서 주고받는 generate 요청 필드를 검증하는 스키마입니다.
    """

    profile: str = "hidden"
    force: bool = False


class DataValidateRequest(BaseModel):
    """API에서 주고받는 데이터 validate 요청 필드를 검증하는 스키마입니다.
    """

    force: bool = True


class ToolCompileRequest(BaseModel):
    """API에서 주고받는 도구 컴파일 요청 필드를 검증하는 스키마입니다.
    """

    tool: str | None = None


class SolutionVerifyRequest(BaseModel):
    """API에서 주고받는 솔루션 verify 요청 필드를 검증하는 스키마입니다.
    """

    profile: str = "hidden"
    solutions: list[str] | None = None


class SolutionStressRequest(BaseModel):
    """API에서 주고받는 솔루션 스트레스 테스트 요청 필드를 검증하는 스키마입니다.
    """

    profile: str = "hidden"
    duration_seconds: int = Field(default=60, ge=1)
    max_cases: int | None = Field(default=None, ge=1)
    solutions: list[str] | None = None
    stop_on_first_mismatch: bool = True


class StressAppendRequest(BaseModel):
    """API에서 주고받는 스트레스 테스트 append 요청 필드를 검증하는 스키마입니다.
    """

    profile: str = "hidden"
    mode: str = Field(default="fixed", pattern="^(fixed|generator)$")
    name: str | None = None


class SolutionCreateRequest(BaseModel):
    """API에서 주고받는 솔루션 create 요청 필드를 검증하는 스키마입니다.
    """

    name: str = Field(min_length=1)
    expected: str = "wa"
    language: str = "cpp"


class SolutionRenameRequest(BaseModel):
    """API에서 주고받는 솔루션 rename 요청 필드를 검증하는 스키마입니다.
    """

    path: str = Field(min_length=1)
    name: str = Field(min_length=1)
    expected: str = "wa"
    language: str = "cpp"


class PackBuildRequest(BaseModel):
    """API에서 주고받는 문제팩 build 요청 필드를 검증하는 스키마입니다.
    """

    pack_id: str = Field(min_length=1)
    platform_id: str | None = None
    verify_profile: str = "hidden"


class BulkPackBuildRequest(BaseModel):
    """API에서 주고받는 일괄 작업 문제팩 build 요청 필드를 검증하는 스키마입니다.
    """

    pack_id: str = Field(min_length=1)
    platform_id: str | None = None
    verify_profile: str = "hidden"
    force: bool = False
    max_workers: int | None = Field(default=None, ge=1, le=16)
    problem_ids: list[str] | None = None
