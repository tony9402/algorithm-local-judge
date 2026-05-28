"""schemas 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PackInstallRequest(BaseModel):
    """PackInstallRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    archive_path: str = Field(min_length=1)


class PackDownloadRequest(BaseModel):
    """PackDownloadRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    repository: str | None = None
    asset_name: str | None = None
    ref: str | None = None


class GenerateRequest(BaseModel):
    """GenerateRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    problem_id: str = Field(min_length=1)
    profile: str | None = None
    force: bool = False


class CasesCompileRequest(BaseModel):
    """CasesCompileRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    problem_id: str = Field(min_length=1)
    profile: str | None = None


class ProblemFolderUpdateRequest(BaseModel):
    """ProblemFolderUpdateRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    folder: str = ""


class RunRequest(BaseModel):
    """RunRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    problem_id: str = Field(min_length=1)
    profile: str | None = None
    source_mode: str = Field(pattern="^(path|upload|text)$")
    source_path: str | None = None
    source_text: str | None = None
    filename: str | None = None


class CacheClearRequest(BaseModel):
    """CacheClearRequest 클래스를 정의하고 동작을 설명합니다.
    
    Args:
        없음
    
    Returns:
        None: 처리 결과를 반환합니다.
    """

    problem: str | None = None
    profile: str | None = None
    runs: bool = False
    all_entries: bool = False
    dry_run: bool = True
