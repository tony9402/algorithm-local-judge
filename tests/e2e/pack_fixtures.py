from __future__ import annotations

import hashlib
import io
import json
import stat
import tarfile
import tempfile
from pathlib import Path
from typing import Any
from zipfile import ZipFile, ZipInfo


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def create_minimal_pack(target: Path, pack_id: str = "e2e-pack", problem_id: str = "e2e") -> Path:
    """Create a valid lightweight .aljpack archive for browser upload tests."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="alj-e2e-pack-") as tmp:
        pack_root = Path(tmp) / pack_id
        problem_root = pack_root / "problems" / problem_id
        tool_root = problem_root / "compiled-tools" / "e2e-platform"
        (problem_root / "generator").mkdir(parents=True)
        tool_root.mkdir(parents=True)

        files: dict[str, bytes] = {
            "pack.json": json.dumps(
                {
                    "schemaVersion": 1,
                    "packId": pack_id,
                    "name": "E2E problem pack",
                    "version": "1",
                    "engineVersion": "0.1.0",
                    "supportedPlatforms": ["e2e-platform"],
                    "problems": [problem_id],
                },
                ensure_ascii=False,
                indent=2,
            ).encode(),
            f"problems/{problem_id}/problem.json": json.dumps(
                {
                    "schemaVersion": 1,
                    "problemId": problem_id,
                    "title": "E2E Pack Problem",
                    "version": 1,
                    "defaultProfile": "hidden",
                    "tools": {
                        "mode": "precompiled",
                        "generatorConfig": "generator/cases.yml",
                        "generator": "compiled-tools/e2e-platform/generator",
                        "validator": "compiled-tools/e2e-platform/validator",
                        "checker": "compiled-tools/e2e-platform/checker",
                        "solution": "compiled-tools/e2e-platform/solution",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ).encode(),
            f"problems/{problem_id}/generator/cases.yml": (
                b"profiles:\n"
                b"  hidden:\n"
                b"    cases:\n"
                b"      - name: sample\n"
                b"        type: fixed\n"
                b"        content: |\n"
                b"          1\n"
            ),
        }
        for name in ["generator", "validator", "checker", "solution"]:
            files[f"problems/{problem_id}/compiled-tools/e2e-platform/{name}"] = (
                b"#!/bin/sh\nexit 0\n"
            )

        manifest_files = []
        for relative, content in files.items():
            path = pack_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            if "/compiled-tools/" in relative:
                path.chmod(0o755)
            manifest_files.append({"path": relative, "sha256": sha256_bytes(content)})

        manifest = {
            "schemaVersion": 1,
            "packId": pack_id,
            "version": "1",
            "platformId": "e2e-platform",
            "files": sorted(manifest_files, key=lambda item: item["path"]),
        }
        (pack_root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with tarfile.open(target, "w:gz") as archive:
            archive.add(pack_root, arcname=pack_id)
    return target


def create_runnable_minimal_pack(
    target: Path,
    pack_id: str = "e2e-pack",
    problem_id: str = "e2e",
) -> Path:
    """Create a lightweight .aljpack that is valid enough for install/generate/run E2E."""
    return create_minimal_pack(target, pack_id=pack_id, problem_id=problem_id)


def sse_event(event: str, data: dict[str, Any]) -> str:
    """Return one Server-Sent Events block for route-mocked browser E2E tests."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_stream(*events: tuple[str, dict[str, Any]]) -> str:
    """Return a complete Server-Sent Events response body."""
    return "".join(sse_event(event, data) for event, data in events)


def create_source_package(root: Path, problem_id: str = "alpha") -> Path:
    """Create a lightweight source package with one discoverable problem."""
    package_root = root / "source-package"
    problem_root = package_root / "problems" / problem_id
    problem_root.mkdir(parents=True, exist_ok=True)
    (package_root / "testlib.h").write_text("// e2e testlib\n", encoding="utf-8")
    (problem_root / "problem.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "problemId": problem_id,
                "title": "Alpha Source Problem",
                "version": 1,
                "defaultProfile": "sample",
                "tools": {
                    "generatorConfig": "generator/cases.yml",
                    "generator": "generator/generator.cpp",
                    "validator": "validator/validator.cpp",
                    "checker": "checker/checker.cpp",
                    "solution": "solutions/main.cpp",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return package_root


def create_source_archive(target: Path, problem_id: str = "beta") -> Path:
    """Create a zip archive containing a source package."""
    with tempfile.TemporaryDirectory(prefix="alj-e2e-source-") as tmp:
        package = create_source_package(Path(tmp), problem_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(target, "w") as archive:
            for path in package.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(package.parent).as_posix())
    return target


def create_unsafe_tar(target: Path) -> Path:
    """Create a tar archive with an unsafe member path."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as archive:
        info = tarfile.TarInfo("../escaped.txt")
        payload = b"unsafe"
        info.size = len(payload)
        archive.addfile(info, fileobj=io.BytesIO(payload))
    return target


def create_unsafe_tar_link(target: Path, *, hardlink: bool = False) -> Path:
    """Create a tar archive with a symlink or hardlink member."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as archive:
        root = tarfile.TarInfo("pack")
        root.type = tarfile.DIRTYPE
        archive.addfile(root)
        info = tarfile.TarInfo("pack/link")
        info.type = tarfile.LNKTYPE if hardlink else tarfile.SYMTYPE
        info.linkname = "pack/target.txt"
        archive.addfile(info)
    return target


def create_unsafe_zip(target: Path) -> Path:
    """Create a zip archive with an unsafe member path."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(target, "w") as archive:
        archive.writestr("../escaped.txt", "unsafe")
    return target


def create_unsafe_zip_symlink(target: Path) -> Path:
    """Create a zip archive with a Unix symlink member."""
    target.parent.mkdir(parents=True, exist_ok=True)
    info = ZipInfo("package/problems/alpha/problem.json")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(target, "w") as archive:
        archive.writestr(info, "target")
    return target
