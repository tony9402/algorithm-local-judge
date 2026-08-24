"""Validate the supported macOS and Linux installation documentation."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_OSES = ("macos", "linux")
OS_LABELS = {"macos": "macOS", "linux": "Linux"}
FENCE_RE = re.compile(r"```(?P<language>[A-Za-z0-9_-]+)\n(?P<body>.*?)\n```", re.DOTALL)
EXPECTED_INSTALL_COMMANDS = (
    "git clone https://github.com/tony9402/algorithm-local-judge.git",
    "cd algorithm-local-judge",
    "./install.sh",
    'export PATH="$HOME/.local/bin:$PATH"',
)
CURL_INSTALL_COMMAND = (
    "curl -fsSL "
    "https://raw.githubusercontent.com/tony9402/algorithm-local-judge/main/install.sh | bash"
)
FORBIDDEN_INSTALL_PATTERNS = (
    re.compile(r"\binstall\.ps1\b", re.IGNORECASE),
    re.compile(r"^\s*winget\s+install\b", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*Set-Location\b", re.MULTILINE | re.IGNORECASE),
)


class InstallDocsError(ValueError):
    """Raised when the installation contract is inconsistent."""


def parse_install_commands(text: str, os_name: str) -> tuple[str, ...]:
    if os_name not in SUPPORTED_OSES:
        raise InstallDocsError(f"unsupported install documentation OS: {os_name}")
    label = OS_LABELS[os_name]
    start_marker = f"<!-- alj-install:start os={os_name} -->"
    end_marker = f"<!-- alj-install:end os={os_name} -->"
    if text.count(start_marker) != 1 or text.count(end_marker) != 1:
        raise InstallDocsError(f"README must contain exactly one {label} install block")
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    block = text[start:end]
    fences = list(FENCE_RE.finditer(block))
    if len(fences) != 1 or fences[0].group("language").lower() != "bash":
        raise InstallDocsError(f"{label} install block must contain exactly one bash code block")
    return tuple(line.strip() for line in fences[0].group("body").splitlines() if line.strip())


def parse_linux_install_commands(text: str) -> tuple[str, ...]:
    """Compatibility wrapper used by external documentation checks."""
    return parse_install_commands(text, "linux")


def validate_no_windows_install_commands(text: str, *, document: str) -> None:
    for pattern in FORBIDDEN_INSTALL_PATTERNS:
        if pattern.search(text):
            raise InstallDocsError(f"{document} contains an unsupported Windows install command")


def validate_install_docs(readme: Path, install_guide: Path, installer: Path) -> None:
    readme_text = readme.read_text(encoding="utf-8")
    for os_name in SUPPORTED_OSES:
        commands = parse_install_commands(readme_text, os_name)
        if commands != EXPECTED_INSTALL_COMMANDS:
            label = OS_LABELS[os_name]
            raise InstallDocsError(
                f"README {label} install commands do not match the supported clone flow"
            )
    validate_no_windows_install_commands(readme_text, document="README")
    for required in (
        "## macOS 설치",
        "## Linux 설치",
        CURL_INSTALL_COMMAND,
        "problems/",
        "tony9402/algorithm-package",
        "judge problem install",
        "~/Library/Application Support/algorithm-local-judge/runtime",
        "${XDG_DATA_HOME:-$HOME/.local/share}/algorithm-local-judge/runtime",
        "~/.local/bin",
        "[macOS 및 Linux 설치·운영 안내](INSTALL.md)",
    ):
        if required not in readme_text:
            raise InstallDocsError(f"README installation guidance is incomplete: {required}")
    if "./algorithm-local-judge/bin/" in readme_text or "./.venv/bin/" in readme_text:
        raise InstallDocsError("README still exposes an internal installation layout")

    guide_text = install_guide.read_text(encoding="utf-8")
    validate_no_windows_install_commands(guide_text, document="INSTALL.md")
    for required in (
        "# macOS 및 Linux 설치·운영 안내",
        *EXPECTED_INSTALL_COMMANDS,
        CURL_INSTALL_COMMAND,
        "./install.sh [--python PATH] [--install-dir PATH] [--bin-dir PATH] [--skip-checks]",
        "judge problem install tony9402/algorithm-package",
        "git pull --ff-only",
        "git worktree add",
        'rm -rf "$HOME/Library/Application Support/algorithm-local-judge/runtime"',
        'rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/algorithm-local-judge/runtime"',
        "~/Library/Caches/algorithm-local-judge",
        "ALJ_DATA_HOME",
    ):
        if required not in guide_text:
            raise InstallDocsError(f"INSTALL.md lifecycle guidance is incomplete: {required}")

    installer_text = installer.read_text(encoding="utf-8")
    for required in (
        'case "$(uname -s)" in',
        "Linux)",
        "Darwin)",
        "현재 설치 스크립트는 macOS와 Linux만 지원합니다.",
        "python3 python",
        "uv sync --frozen --no-dev --no-editable",
        '--python "$INSTALL_PYTHON"',
        "-m venv",
        '"$runtime_dir/pyvenv.cfg"',
        "sys.prefix != sys.base_prefix",
        "fallback 없이 설치를 중단합니다.",
        'DATA_BASE="${XDG_DATA_HOME:-$HOME/.local/share}"',
        'INSTALL_DIR="$HOME/Library/Application Support/algorithm-local-judge/runtime"',
        'BIN_DIR="$HOME/.local/bin"',
        "ln -s",
        "Added by algorithm-local-judge installer.",
        "judge problem install tony9402/algorithm-package",
        "ALJ_INSTALL_REPOSITORY:-tony9402/algorithm-local-judge",
        "ALJ_INSTALL_REF:-main",
        'mktemp -d "${TMPDIR:-/tmp}/alj-bootstrap.XXXXXX"',
        "git clone --quiet --depth 1 --single-branch",
        'bash "$source_dir/install.sh" "${INSTALL_ARGS[@]}"',
    ):
        if required not in installer_text:
            raise InstallDocsError(f"install.sh contract is incomplete: {required}")
    if '--editable "$ROOT_DIR"' in installer_text:
        raise InstallDocsError(
            "install.sh must not depend on the source checkout after installation"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", type=Path, default=ROOT / "README.md")
    parser.add_argument("--install-guide", type=Path, default=ROOT / "INSTALL.md")
    parser.add_argument("--installer", type=Path, default=ROOT / "install.sh")
    args = parser.parse_args()
    try:
        validate_install_docs(
            args.readme.resolve(),
            args.install_guide.resolve(),
            args.installer.resolve(),
        )
    except (InstallDocsError, OSError) as exc:
        print(f"error: {exc}")
        return 1
    print("macOS and Linux installation documentation contract is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
