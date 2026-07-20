"""Validate README installation blocks against verified distribution channel state."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_OS = ("macos", "ubuntu-debian", "fedora", "windows")
START_RE = re.compile(
    r"<!-- alj-install:start os=(?P<os>[a-z-]+) status=(?P<status>published|unpublished) -->"
)
FENCE_RE = re.compile(r"```(?P<language>[A-Za-z0-9_-]+)\n(?P<body>.*?)\n```", re.DOTALL)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_PREREQUISITE_RE = re.compile(r"\b(?:python3?|uv|git|cosign)\b", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(
    r"(?:<[^>]+>|\{\{.*?\}\}|TODO|TBD|example\.com|\.invalid|/latest/|\blatest\b)",
    re.IGNORECASE,
)
UNPUBLISHED_COMMAND_RE = re.compile(
    r"^\s*(?:\$|sudo\b|brew\b|apt(?:-get)?\b|dnf\b|winget\b|curl\b|wget\b|judge\b|powershell\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InstallBlock:
    os_id: str
    status: str
    language: str
    lines: tuple[str, ...]


def parse_blocks(text: str) -> dict[str, InstallBlock]:
    blocks = {}
    starts = list(START_RE.finditer(text))
    for match in starts:
        end = text.find("<!-- alj-install:end -->", match.end())
        if end < 0:
            raise JudgeError(f"README install block has no end marker: {match.group('os')}")
        body = text[match.end() : end]
        fences = list(FENCE_RE.finditer(body))
        if len(fences) != 1:
            raise JudgeError(
                f"README install block must contain one code block: {match.group('os')}"
            )
        fence = fences[0]
        lines = tuple(line.strip() for line in fence.group("body").splitlines() if line.strip())
        os_id = match.group("os")
        if os_id in blocks:
            raise JudgeError(f"README contains duplicate install block: {os_id}")
        blocks[os_id] = InstallBlock(
            os_id,
            match.group("status"),
            fence.group("language").lower(),
            lines,
        )
    if set(blocks) != set(REQUIRED_OS):
        missing = sorted(set(REQUIRED_OS) - set(blocks))
        unknown = sorted(set(blocks) - set(REQUIRED_OS))
        detail = [f"missing={','.join(missing)}" if missing else ""]
        detail.append(f"unknown={','.join(unknown)}" if unknown else "")
        raise JudgeError(
            f"README install OS blocks are incomplete: {' '.join(filter(None, detail))}"
        )
    return blocks


def load_channels(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise JudgeError(f"install channel state is invalid: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        raise JudgeError("install channel state has an unsupported schemaVersion")
    channels = payload.get("channels")
    if not isinstance(channels, dict) or set(channels) != set(REQUIRED_OS):
        raise JudgeError("install channel state must define every supported OS exactly once")
    return channels


def validate_published_channel(block: InstallBlock, channel: dict[str, Any]) -> None:
    if block.language not in {"bash", "shell", "powershell"}:
        raise JudgeError(f"published install block must be executable: {block.os_id}")
    if FORBIDDEN_PREREQUISITE_RE.search("\n".join(block.lines)):
        raise JudgeError(
            f"published install commands contain a hidden prerequisite: {block.os_id}"
        )
    if PLACEHOLDER_RE.search("\n".join(block.lines)):
        raise JudgeError(
            f"published install commands contain a placeholder/channel: {block.os_id}"
        )
    if any(
        line.startswith(("#", "REM "))
        or any(separator in line for separator in ("&&", "||", ";", " | "))
        for line in block.lines
    ):
        raise JudgeError(
            f"published install block must contain one command per line: {block.os_id}"
        )
    configured = channel.get("installCommands")
    if not isinstance(configured, list) or configured != list(block.lines):
        raise JudgeError(f"README commands do not match verified channel state: {block.os_id}")
    if "judge setup --yes" not in block.lines[-1]:
        raise JudgeError(f"published install block must finish first-run setup: {block.os_id}")
    smoke_commands = channel.get("smokeInstallCommands")
    if not isinstance(smoke_commands, list) or not 1 <= len(smoke_commands) <= 3:
        raise JudgeError(f"published channel has no N-1 smoke install commands: {block.os_id}")
    if FORBIDDEN_PREREQUISITE_RE.search("\n".join(smoke_commands)) or PLACEHOLDER_RE.search(
        "\n".join(smoke_commands)
    ):
        raise JudgeError(f"published smoke install contains a hidden prerequisite: {block.os_id}")
    for field in (
        "upgradeCommand",
        "rollbackCommand",
        "uninstallCommand",
        "releaseVersion",
        "rollbackVersion",
        "sampleProblem",
    ):
        if not isinstance(channel.get(field), str) or not channel[field].strip():
            raise JudgeError(
                f"published channel lifecycle field is missing: {block.os_id}.{field}"
            )
    samples = channel.get("samples")
    if not isinstance(samples, dict) or set(samples) != {"cpp", "python", "pypy", "java"}:
        raise JudgeError(f"published channel must define four language samples: {block.os_id}")
    if not all(isinstance(value, str) and value.strip() for value in samples.values()):
        raise JudgeError(f"published channel has an empty language sample: {block.os_id}")
    evidence = channel.get("evidence")
    if not isinstance(evidence, dict) or not SHA256_RE.fullmatch(
        str(evidence.get("releaseManifestSha256") or "")
    ):
        raise JudgeError(f"published channel has no release manifest evidence: {block.os_id}")
    if not SHA256_RE.fullmatch(str(evidence.get("cleanOsAttestationSha256") or "")):
        raise JudgeError(f"published channel has no clean-OS attestation: {block.os_id}")
    if not isinstance(evidence.get("verifiedAt"), str) or not evidence["verifiedAt"].strip():
        raise JudgeError(f"published channel has no clean-OS verification time: {block.os_id}")


def validate_unpublished_channel(block: InstallBlock, channel: dict[str, Any]) -> None:
    if block.language != "text":
        raise JudgeError(f"unpublished install block must not be executable: {block.os_id}")
    if any(UNPUBLISHED_COMMAND_RE.search(line) for line in block.lines):
        raise JudgeError(f"unpublished install block exposes a command: {block.os_id}")
    if channel.get("installCommands") not in ([], None):
        raise JudgeError(f"unpublished channel contains install commands: {block.os_id}")
    if channel.get("smokeInstallCommands") not in ([], None):
        raise JudgeError(f"unpublished channel contains smoke install commands: {block.os_id}")


def validate_no_unpublished_commands(text: str, channels: dict[str, dict[str, Any]]) -> None:
    checks = {
        "macos": re.compile(
            r"^\s*brew\s+install\b.*algorithm-local", re.MULTILINE | re.IGNORECASE
        ),
        "ubuntu-debian": re.compile(
            r"^\s*(?:sudo\s+)?apt(?:-get)?\s+install\b.*algorithm-local",
            re.MULTILINE | re.IGNORECASE,
        ),
        "fedora": re.compile(
            r"^\s*(?:sudo\s+)?dnf\s+install\b.*algorithm-local",
            re.MULTILINE | re.IGNORECASE,
        ),
        "windows": re.compile(r"^\s*winget\s+install\b", re.MULTILINE | re.IGNORECASE),
    }
    if "raw.githubusercontent.com" in text and "install_local.sh" in text:
        raise JudgeError("README publishes an unverified raw-branch installer command")
    for os_id, pattern in checks.items():
        if channels[os_id].get("status") != "published" and pattern.search(text):
            raise JudgeError(f"README publishes an unverified {os_id} install channel")


def validate_install_docs(readme: Path, channel_state: Path, *, stable: bool = False) -> None:
    text = readme.read_text(encoding="utf-8")
    blocks = parse_blocks(text)
    channels = load_channels(channel_state)
    validate_no_unpublished_commands(text, channels)
    for os_id in REQUIRED_OS:
        block = blocks[os_id]
        channel = channels[os_id]
        status = channel.get("status")
        if status not in {"published", "unpublished"} or block.status != status:
            raise JudgeError(f"README/channel publication status mismatch: {os_id}")
        if not 2 <= len(block.lines) <= 3:
            raise JudgeError(f"install block must contain 2 to 3 lines: {os_id}")
        if status == "published":
            validate_published_channel(block, channel)
        else:
            validate_unpublished_channel(block, channel)
            if stable:
                raise JudgeError(f"stable install gate is blocked by unpublished channel: {os_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", type=Path, default=ROOT / "README.md")
    parser.add_argument(
        "--channels",
        type=Path,
        default=ROOT / "packaging" / "install-channels.json",
    )
    parser.add_argument("--stable", action="store_true")
    args = parser.parse_args()
    try:
        validate_install_docs(args.readme.resolve(), args.channels.resolve(), stable=args.stable)
    except (JudgeError, OSError) as exc:
        print(f"error: {exc}")
        return 1
    print("Install documentation contract is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
