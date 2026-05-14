from __future__ import annotations

from pydantic import BaseModel, Field


class PackInstallRequest(BaseModel):
    """Request body for installing a local problem pack."""

    archive_path: str = Field(min_length=1)


class PackDownloadRequest(BaseModel):
    """Request body for downloading an official problem pack."""

    repository: str | None = None
    asset_name: str | None = None


class GenerateRequest(BaseModel):
    """Request body for generating test data."""

    problem_id: str = Field(min_length=1)
    profile: str | None = None
    force: bool = False


class CasesCompileRequest(BaseModel):
    """Request body for compiling a cases.yml profile."""

    problem_id: str = Field(min_length=1)
    profile: str | None = None


class RunRequest(BaseModel):
    """Request body for judging a local path or pasted source code."""

    problem_id: str = Field(min_length=1)
    profile: str | None = None
    source_mode: str = Field(pattern="^(path|upload|text)$")
    source_path: str | None = None
    source_text: str | None = None
    filename: str | None = None


class CacheClearRequest(BaseModel):
    """Request body for previewing or applying cache deletion."""

    problem: str | None = None
    profile: str | None = None
    runs: bool = False
    all_entries: bool = False
    dry_run: bool = True
