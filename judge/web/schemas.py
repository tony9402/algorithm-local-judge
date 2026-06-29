"""schemas 웹 백엔드 구성과 응답 데이터 조립을 담당합니다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PackInstallRequest(BaseModel):
    """API에서 주고받는 문제팩 설치 요청 필드를 검증하는 스키마입니다.
    """

    archive_path: str = Field(min_length=1)


class PackDownloadRequest(BaseModel):
    """API에서 주고받는 문제팩 다운로드 요청 필드를 검증하는 스키마입니다.
    """

    repository: str | None = None
    asset_name: str | None = None
    ref: str | None = None


class GenerateRequest(BaseModel):
    """API에서 주고받는 generate 요청 필드를 검증하는 스키마입니다.
    """

    problem_id: str = Field(min_length=1)
    profile: str | None = None
    force: bool = False


class CasesCompileRequest(BaseModel):
    """API에서 주고받는 케이스 컴파일 요청 필드를 검증하는 스키마입니다.
    """

    problem_id: str = Field(min_length=1)
    profile: str | None = None


class ProblemFolderUpdateRequest(BaseModel):
    """API에서 주고받는 문제 폴더 update 요청 필드를 검증하는 스키마입니다.
    """

    folder: str = ""


class ProblemFolderCreateRequest(BaseModel):
    """API에서 주고받는 문제 폴더 create 요청 필드를 검증하는 스키마입니다."""

    folder: str = Field(min_length=1)


class ProblemFolderDeleteRequest(BaseModel):
    """API에서 주고받는 문제 폴더 delete 요청 필드를 검증하는 스키마입니다."""

    folder: str = Field(min_length=1)
    confirm_delete_problems: bool = False


class RunRequest(BaseModel):
    """API에서 주고받는 실행 요청 필드를 검증하는 스키마입니다.
    """

    problem_id: str = Field(min_length=1)
    profile: str | None = None
    source_mode: str = Field(pattern="^(path|upload|text)$")
    source_path: str | None = None
    source_text: str | None = None
    filename: str | None = None
    language: str | None = None


class CacheClearRequest(BaseModel):
    """API에서 주고받는 캐시 clear 요청 필드를 검증하는 스키마입니다.
    """

    problem: str | None = None
    profile: str | None = None
    runs: bool = False
    all_entries: bool = False
    dry_run: bool = True
