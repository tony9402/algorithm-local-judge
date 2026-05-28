"""schemas 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkspaceOpenRequest(BaseModel):
    """WorkspaceOpenRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    path: str = Field(min_length=1)


class GitCloneRequest(BaseModel):
    """GitCloneRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    url: str = Field(min_length=1)
    path: str = Field(min_length=1)
    branch: str | None = None


class GitCommitRequest(BaseModel):
    """GitCommitRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    message: str = Field(min_length=1)
    files: list[str] | None = None


class RepositorySelectRequest(BaseModel):
    """RepositorySelectRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    repo_name: str = Field(min_length=1)


class RepositoryCloneRequest(BaseModel):
    """RepositoryCloneRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    url: str = Field(min_length=1)
    branch: str | None = None
    repo_name: str | None = None


class RepositoryRegisterRequest(BaseModel):
    """RepositoryRegisterRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    repo_name: str = Field(min_length=1)


class ProblemCreateRequest(BaseModel):
    """ProblemCreateRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    problem_id: str = Field(min_length=1)
    title: str = "Untitled Problem"
    folder: str = ""
    version: int = 1
    default_profile: str = "hidden"
    limits: dict[str, Any] | None = None


class ProblemDeleteRequest(BaseModel):
    """ProblemDeleteRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    confirm_phrase: str = Field(min_length=1)


class ProblemRenameRequest(BaseModel):
    """ProblemRenameRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    problem_id: str = Field(min_length=1)


class MetadataPatchRequest(BaseModel):
    """MetadataPatchRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    metadata: dict[str, Any]


class FileWriteRequest(BaseModel):
    """FileWriteRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    content: str


class CasesCompileRequest(BaseModel):
    """CasesCompileRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    profile: str | None = None


class GenerateRequest(BaseModel):
    """GenerateRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    profile: str = "hidden"
    force: bool = False


class DataValidateRequest(BaseModel):
    """DataValidateRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    force: bool = True


class ToolCompileRequest(BaseModel):
    """ToolCompileRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    tool: str | None = None


class SolutionVerifyRequest(BaseModel):
    """SolutionVerifyRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    profile: str = "hidden"
    solutions: list[str] | None = None


class SolutionStressRequest(BaseModel):
    """SolutionStressRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    profile: str = "hidden"
    duration_seconds: int = Field(default=60, ge=1)
    max_cases: int | None = Field(default=None, ge=1)
    solutions: list[str] | None = None
    stop_on_first_mismatch: bool = True


class StressAppendRequest(BaseModel):
    """StressAppendRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    profile: str = "hidden"
    mode: str = Field(default="fixed", pattern="^(fixed|generator)$")
    name: str | None = None


class SolutionCreateRequest(BaseModel):
    """SolutionCreateRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    name: str = Field(min_length=1)
    expected: str = "wa"
    language: str = "cpp"


class SolutionRenameRequest(BaseModel):
    """SolutionRenameRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    path: str = Field(min_length=1)
    name: str = Field(min_length=1)
    expected: str = "wa"
    language: str = "cpp"


class PackBuildRequest(BaseModel):
    """PackBuildRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    pack_id: str = Field(min_length=1)
    platform_id: str | None = None
    verify_profile: str = "hidden"


class BulkPackBuildRequest(BaseModel):
    """BulkPackBuildRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    pack_id: str = Field(min_length=1)
    platform_id: str | None = None
    verify_profile: str = "hidden"
    force: bool = False
    max_workers: int | None = Field(default=None, ge=1, le=16)
    problem_ids: list[str] | None = None
