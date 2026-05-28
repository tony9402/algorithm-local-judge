from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from judge.core.errors import JudgeError
from judge.core.pack import installed_packs
from judge.core.paths import (
    app_root,
    cache_root,
    current_platform_id,
    problem_pack_root,
    problem_source_root,
    repo_root,
    user_data_root,
)
from judge.core.remote_github import official_pack_repository

DOCTOR_SCHEMA_VERSION = 1
INSTALL_HINTS = {
    "cpp": (
        "Install Xcode Command Line Tools on macOS, build-essential on Linux, "
        "or MSYS2/MinGW on Windows."
    ),
    "javaCompiler": "Install a JDK and set ALJ_JAVAC when javac is not on PATH.",
    "javaRuntime": "Install a JDK/JRE and set ALJ_JAVA when java is not on PATH.",
    "git": "Install Git and make sure the git command is on PATH.",
}


def tool_status(
    label: str,
    candidates: list[str],
    env_name: str | None = None,
    hint_key: str | None = None,
) -> dict[str, Any]:
    """Return diagnostic status for a command-line tool."""
    configured = os.environ.get(env_name) if env_name else None
    checked = [configured] if configured else candidates
    resolved = None
    for candidate in checked:
        if not candidate:
            continue
        if Path(candidate).is_absolute() and Path(candidate).exists():
            resolved = candidate
            break
        path = shutil.which(candidate)
        if path:
            resolved = path
            break
    return {
        "label": label,
        "status": "ok" if resolved else "missing",
        "path": resolved,
        "env": env_name,
        "configured": configured,
        "candidates": candidates,
        "installHint": INSTALL_HINTS.get(hint_key or label, ""),
    }


def path_status(label: str, path: Path) -> dict[str, Any]:
    """Return diagnostic status for a runtime path."""
    return {
        "label": label,
        "status": "ok" if path.exists() else "missing",
        "path": str(path),
        "exists": path.exists(),
        "isDir": path.is_dir(),
    }


def collect_diagnostics() -> dict[str, Any]:
    """Collect local environment diagnostics for the judge CLI."""
    packs = installed_packs()
    try:
        official_repository = official_pack_repository()
        official_repository_status = "ok"
        official_repository_error = None
    except JudgeError as exc:
        official_repository = None
        official_repository_status = "warning"
        official_repository_error = str(exc)
    tools = {
        "cpp": tool_status("C++ compiler", ["g++"], hint_key="cpp"),
        "javaCompiler": tool_status(
            "Java compiler",
            ["javac"],
            "ALJ_JAVAC",
            hint_key="javaCompiler",
        ),
        "javaRuntime": tool_status(
            "Java runtime",
            ["java"],
            "ALJ_JAVA",
            hint_key="javaRuntime",
        ),
        "git": tool_status("Git", ["git"], hint_key="git"),
    }
    paths = {
        "projectRoot": path_status("Project root", repo_root()),
        "appRoot": path_status("Application root", app_root()),
        "dataHome": path_status("Data home", user_data_root()),
        "cacheHome": path_status("Cache home", cache_root()),
        "packHome": path_status("Problem pack home", problem_pack_root()),
        "sourceHome": path_status("Problem source home", problem_source_root()),
    }
    required_statuses = [
        "ok",
        tools["cpp"]["status"],
        paths["projectRoot"]["status"],
        official_repository_status,
    ]
    status = "ok" if all(value == "ok" for value in required_statuses) else "warning"
    return {
        "schemaVersion": DOCTOR_SCHEMA_VERSION,
        "status": status,
        "platformId": current_platform_id(),
        "python": {
            "status": "ok",
            "path": sys.executable,
            "version": platform.python_version(),
        },
        "tools": tools,
        "paths": paths,
        "installedPacks": {
            "status": "ok",
            "count": len(packs),
            "packs": [
                {
                    "packId": pack.get("packId"),
                    "version": pack.get("version"),
                    "path": pack.get("path"),
                    "problems": pack.get("problems", []),
                }
                for pack in packs
            ],
        },
        "officialRepository": {
            "status": official_repository_status,
            "repository": official_repository,
            "error": official_repository_error,
        },
    }


def status_icon(status: str) -> str:
    """Return a compact ASCII status marker."""
    return "OK" if status == "ok" else "WARN"


def print_text_report(diagnostics: dict[str, Any], verbose: bool) -> None:
    """Print human-readable diagnostics."""
    print(f"Judge doctor: {diagnostics['status']}")
    print(f"Platform: {diagnostics['platformId']}")
    python = diagnostics["python"]
    print(f"Python: {status_icon(python['status'])} {python['version']} ({python['path']})")

    print("Tools:")
    for key in ("cpp", "javaCompiler", "javaRuntime", "git"):
        tool = diagnostics["tools"][key]
        value = tool["path"] or ", ".join(tool["candidates"])
        print(f"  {tool['label']}: {status_icon(tool['status'])} {value}")
        if tool["status"] != "ok" and tool.get("installHint"):
            print(f"    install: {tool['installHint']}")
        if verbose and tool.get("configured"):
            print(f"    configured by {tool['env']}: {tool['configured']}")

    print("Paths:")
    for key in ("projectRoot", "dataHome", "cacheHome", "packHome", "sourceHome"):
        path = diagnostics["paths"][key]
        print(f"  {path['label']}: {status_icon(path['status'])} {path['path']}")
        if verbose:
            print(f"    exists: {path['exists']}  dir: {path['isDir']}")

    installed = diagnostics["installedPacks"]
    print(f"Installed packs: {installed['count']}")
    if verbose and installed["packs"]:
        for pack in installed["packs"]:
            problems = ", ".join(pack.get("problems") or [])
            print(f"  {pack.get('packId')} {pack.get('version') or ''} problems: {problems}")
            if pack.get("path"):
                print(f"    {pack['path']}")

    official = diagnostics["officialRepository"]
    repository = official["repository"] or official["error"]
    print(f"Official repository: {status_icon(official['status'])} {repository}")


def handle(args: argparse.Namespace) -> int:
    """Handle `judge doctor` diagnostics."""
    diagnostics = collect_diagnostics()
    if args.json:
        print(json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(diagnostics, args.verbose)
    return 0
