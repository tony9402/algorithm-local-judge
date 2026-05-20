from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkspaceOpenRequest(BaseModel):
    """Request body for switching the active workspace."""

    path: str = Field(min_length=1)


class ProblemCreateRequest(BaseModel):
    """Request body for creating a new problem."""

    problem_id: str = Field(min_length=1)
    title: str = "Untitled Problem"
    folder: str = ""
    version: int = 1
    default_profile: str = "hidden"
    limits: dict[str, Any] | None = None


class ProblemDeleteRequest(BaseModel):
    """Request body for deleting a problem."""

    confirm_phrase: str = Field(min_length=1)


class ProblemRenameRequest(BaseModel):
    """Request body for changing a problem id."""

    problem_id: str = Field(min_length=1)


class MetadataPatchRequest(BaseModel):
    """Request body for patching problem metadata."""

    metadata: dict[str, Any]


class FileWriteRequest(BaseModel):
    """Request body for writing a problem file."""

    content: str


class CasesCompileRequest(BaseModel):
    """Request body for cases.yml compilation."""

    profile: str | None = None


class GenerateRequest(BaseModel):
    """Request body for generating problem data."""

    profile: str = "hidden"
    force: bool = False


class DataValidateRequest(BaseModel):
    """Request body for generating and validating every cases.yml profile."""

    force: bool = True


class ToolCompileRequest(BaseModel):
    """Request body for compiling all tools or one selected tool."""

    tool: str | None = None


class SolutionVerifyRequest(BaseModel):
    """Request body for solution expectation verification."""

    profile: str = "hidden"
    solutions: list[str] | None = None


class SolutionCreateRequest(BaseModel):
    """Request body for creating an expected-result solution file."""

    name: str = Field(min_length=1)
    expected: str = "wa"
    language: str = "cpp"


class SolutionRenameRequest(BaseModel):
    """Request body for renaming an expected-result solution file."""

    path: str = Field(min_length=1)
    name: str = Field(min_length=1)
    expected: str = "wa"
    language: str = "cpp"


class PackBuildRequest(BaseModel):
    """Request body for building a source-free problem pack."""

    pack_id: str = Field(min_length=1)
    platform_id: str | None = None
    verify_profile: str = "hidden"


class BulkPackBuildRequest(BaseModel):
    """Request body for testing selected problems and building one pack."""

    pack_id: str = Field(min_length=1)
    platform_id: str | None = None
    verify_profile: str = "hidden"
    force: bool = False
    max_workers: int | None = Field(default=None, ge=1, le=16)
    problem_ids: list[str] | None = None
