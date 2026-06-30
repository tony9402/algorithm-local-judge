"""브라우저와 명령줄 종단 간 테스트가 사용할 최소 패키지, 소스 아카이브, 보안 검증용 아카이브를 생성하는 모듈입니다."""

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
    """다운로드와 패키지 검증 테스트에서 사용할 SHA-256 체크섬 문자열을 계산합니다.

    Args:
        value (bytes): 해시하거나 입력창에 설정하거나 비교할 값입니다.

    Returns:
        str: 입력 바이트열의 SHA-256 해시를 16진수 문자열로 표현한 값입니다.
    """
    return hashlib.sha256(value).hexdigest()


def create_minimal_pack(target: Path, pack_id: str = "e2e-pack", problem_id: str = "e2e") -> Path:
    """최소 패키지 테스트에 필요한 파일 구조와 아카이브를 만들어 설치, 업로드, 보안 검증 경로를 재현합니다.

    Args:
        target (Path): 생성된 파일, 아카이브, 제출 소스를 기록할 경로입니다.
        pack_id (str): 생성하거나 설치할 테스트 패키지 식별자입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.

    Returns:
        Path: 테스트가 생성하거나 조회한 파일 시스템 경로입니다.
    """
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
                b"  sample:\n"
                b"    cases:\n"
                b"      - name: sample\n"
                b"        type: fixed\n"
                b"        content: |\n"
                b"          1\n"
                b"  hidden:\n"
                b"    cases:\n"
                b"      - name: hidden\n"
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
    """실행 가능 최소 패키지 테스트에 필요한 파일 구조와 아카이브를 만들어 설치, 업로드, 보안 검증 경로를 재현합니다.

    Args:
        target (Path): 생성된 파일, 아카이브, 제출 소스를 기록할 경로입니다.
        pack_id (str): 생성하거나 설치할 테스트 패키지 식별자입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.

    Returns:
        Path: 테스트가 생성하거나 조회한 파일 시스템 경로입니다.
    """
    return create_minimal_pack(target, pack_id=pack_id, problem_id=problem_id)


def sse_event(event: str, data: dict[str, Any]) -> str:
    """서버 전송 이벤트 이벤트 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

    Args:
        event (str): 서버 전송 이벤트 블록에 기록할 이벤트 이름입니다.
        data (dict[str, Any]): 스트림 이벤트 본문으로 직렬화할 구조화된 데이터입니다.

    Returns:
        str: 하나의 서버 전송 이벤트 블록 문자열입니다.
    """
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_stream(*events: tuple[str, dict[str, Any]]) -> str:
    """서버 전송 이벤트 스트림 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

    Args:
        events (tuple[str, dict[str, Any]]): 하나의 스트림 본문으로 이어 붙일 서버 전송 이벤트 블록입니다.

    Returns:
        str: 여러 서버 전송 이벤트 블록을 이어 붙인 응답 본문입니다.
    """
    return "".join(sse_event(event, data) for event, data in events)


def create_source_package(root: Path, problem_id: str = "alpha") -> Path:
    """소스 패키지 테스트에 필요한 파일 구조와 아카이브를 만들어 설치, 업로드, 보안 검증 경로를 재현합니다.

    Args:
        root (Path): 픽스처나 임시 작업공간을 생성할 기준 디렉터리입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.

    Returns:
        Path: 테스트용 소스 패키지 디렉터리 경로입니다.
    """
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
    """소스 아카이브 테스트에 필요한 파일 구조와 아카이브를 만들어 설치, 업로드, 보안 검증 경로를 재현합니다.

    Args:
        target (Path): 생성된 파일, 아카이브, 제출 소스를 기록할 경로입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.

    Returns:
        Path: 테스트용 소스 패키지 아카이브 경로입니다.
    """
    with tempfile.TemporaryDirectory(prefix="alj-e2e-source-") as tmp:
        package = create_source_package(Path(tmp), problem_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(target, "w") as archive:
            for path in package.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(package.parent).as_posix())
    return target


def create_unsafe_tar(target: Path) -> Path:
    """안전하지 않은 tar 테스트에 필요한 파일 구조와 아카이브를 만들어 설치, 업로드, 보안 검증 경로를 재현합니다.

    Args:
        target (Path): 생성된 파일, 아카이브, 제출 소스를 기록할 경로입니다.

    Returns:
        Path: 경로 순회 멤버를 포함한 tar 아카이브 경로입니다.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as archive:
        info = tarfile.TarInfo("../escaped.txt")
        payload = b"unsafe"
        info.size = len(payload)
        archive.addfile(info, fileobj=io.BytesIO(payload))
    return target


def create_unsafe_tar_link(target: Path, *, hardlink: bool = False) -> Path:
    """안전하지 않은 tar 링크 테스트에 필요한 파일 구조와 아카이브를 만들어 설치, 업로드, 보안 검증 경로를 재현합니다.

    Args:
        target (Path): 생성된 파일, 아카이브, 제출 소스를 기록할 경로입니다.
        hardlink (bool): tar 링크 픽스처를 하드링크로 만들지 결정하는 플래그입니다.

    Returns:
        Path: 링크 멤버를 포함한 tar 아카이브 경로입니다.
    """
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
    """안전하지 않은 zip 테스트에 필요한 파일 구조와 아카이브를 만들어 설치, 업로드, 보안 검증 경로를 재현합니다.

    Args:
        target (Path): 생성된 파일, 아카이브, 제출 소스를 기록할 경로입니다.

    Returns:
        Path: 경로 순회 멤버를 포함한 zip 아카이브 경로입니다.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(target, "w") as archive:
        archive.writestr("../escaped.txt", "unsafe")
    return target


def create_unsafe_zip_symlink(target: Path) -> Path:
    """안전하지 않은 zip 심볼릭 링크 테스트에 필요한 파일 구조와 아카이브를 만들어 설치, 업로드, 보안 검증 경로를 재현합니다.

    Args:
        target (Path): 생성된 파일, 아카이브, 제출 소스를 기록할 경로입니다.

    Returns:
        Path: 심볼릭 링크 멤버를 포함한 zip 아카이브 경로입니다.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    info = ZipInfo("package/problems/alpha/problem.json")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(target, "w") as archive:
        archive.writestr(info, "target")
    return target
