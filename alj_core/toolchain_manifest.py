"""Versioned managed-toolchain manifest parsing and validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from alj_core.errors import JudgeError

TOOLCHAIN_MANIFEST_SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
REQUIRED_TOOL_IDS = frozenset({"cxx", "javac", "java", "python", "pypy"})


@dataclass(frozen=True)
class ToolchainTool:
    path: str
    sha256: str


@dataclass(frozen=True)
class ToolchainArtifact:
    url: str | None
    sha256: str
    signature: dict[str, str] | None


@dataclass(frozen=True)
class ToolchainLicense:
    name: str | None
    url: str | None


@dataclass(frozen=True)
class ToolchainManifest:
    schema_version: int
    profile_id: str
    version: str
    platform_id: str
    artifact: ToolchainArtifact
    license: ToolchainLicense
    tools: dict[str, ToolchainTool]

    @property
    def provider_configured(self) -> bool:
        signature = self.artifact.signature or {}
        return bool(
            self.artifact.url
            and self.license.name
            and self.license.url
            and signature.get("type")
            and signature.get("value")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "profileId": self.profile_id,
            "version": self.version,
            "platformId": self.platform_id,
            "artifact": {
                "url": self.artifact.url,
                "sha256": self.artifact.sha256,
                "signature": self.artifact.signature,
            },
            "license": {"name": self.license.name, "url": self.license.url},
            "tools": {
                tool_id: {"path": tool.path, "sha256": tool.sha256}
                for tool_id, tool in sorted(self.tools.items())
            },
        }


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise JudgeError(f"toolchain manifest {label} must be an object")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise JudgeError(f"toolchain manifest {label} must be a non-empty string or null")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value.lower()):
        raise JudgeError(f"toolchain manifest {label} must be a SHA-256 digest")
    return value.lower()


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise JudgeError(f"toolchain manifest {label} is invalid")
    return value


def _tool_path(value: object, tool_id: str) -> str:
    if not isinstance(value, str) or not value:
        raise JudgeError(f"toolchain manifest tools.{tool_id}.path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise JudgeError(f"toolchain manifest tools.{tool_id}.path must stay inside the profile")
    return path.as_posix()


def parse_toolchain_manifest(payload: object) -> ToolchainManifest:
    data = _mapping(payload, "root")
    schema_version = data.get("schemaVersion")
    if schema_version != TOOLCHAIN_MANIFEST_SCHEMA_VERSION:
        raise JudgeError(
            "unsupported toolchain manifest schemaVersion: "
            f"{schema_version} (expected {TOOLCHAIN_MANIFEST_SCHEMA_VERSION})"
        )
    artifact_data = _mapping(data.get("artifact"), "artifact")
    license_data = _mapping(data.get("license"), "license")
    signature_value = artifact_data.get("signature")
    signature: dict[str, str] | None = None
    if signature_value is not None:
        signature_data = _mapping(signature_value, "artifact.signature")
        signature = {
            "type": _optional_text(signature_data.get("type"), "artifact.signature.type") or "",
            "value": _optional_text(signature_data.get("value"), "artifact.signature.value") or "",
        }
    tools_data = _mapping(data.get("tools"), "tools")
    missing = sorted(REQUIRED_TOOL_IDS - tools_data.keys())
    unknown = sorted(tools_data.keys() - REQUIRED_TOOL_IDS)
    if missing:
        raise JudgeError(f"toolchain manifest is missing tools: {', '.join(missing)}")
    if unknown:
        raise JudgeError(f"toolchain manifest has unknown tools: {', '.join(unknown)}")
    tools = {}
    for tool_id in sorted(REQUIRED_TOOL_IDS):
        tool_data = _mapping(tools_data[tool_id], f"tools.{tool_id}")
        tools[tool_id] = ToolchainTool(
            path=_tool_path(tool_data.get("path"), tool_id),
            sha256=_sha256(tool_data.get("sha256"), f"tools.{tool_id}.sha256"),
        )
    return ToolchainManifest(
        schema_version=schema_version,
        profile_id=_identifier(data.get("profileId"), "profileId"),
        version=_identifier(data.get("version"), "version"),
        platform_id=_identifier(data.get("platformId"), "platformId"),
        artifact=ToolchainArtifact(
            url=_optional_text(artifact_data.get("url"), "artifact.url"),
            sha256=_sha256(artifact_data.get("sha256"), "artifact.sha256"),
            signature=signature,
        ),
        license=ToolchainLicense(
            name=_optional_text(license_data.get("name"), "license.name"),
            url=_optional_text(license_data.get("url"), "license.url"),
        ),
        tools=tools,
    )


def load_toolchain_manifest(path: Path) -> ToolchainManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise JudgeError(f"could not read toolchain manifest: {path}: {exc}") from exc
    return parse_toolchain_manifest(payload)
