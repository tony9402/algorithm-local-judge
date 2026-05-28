"""checksums 도메인 로직과 파일시스템 변경 정책을 담당합니다.
"""
from __future__ import annotations

import re
from pathlib import Path

from judge.core.errors import JudgeError
from judge.utils.hashing import sha256_file

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def checksum_sidecar_path(artifact_path: Path) -> Path:
    return artifact_path.with_name(f"{artifact_path.name}.sha256")


def parse_sha256_checksum(text: str, artifact_name: str) -> str:
    """sha256 체크섬 원본 입력을 내부 로직이 사용할 구조로 해석합니다.

    Args:
        text (str): 화면에 표시하거나 비교에 사용할 텍스트입니다.
        artifact_name (str): 산출물 이름를 사용자 표시와 내부 조회에 함께 사용하는 이름입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 sha256 체크섬 문자열입니다.
    """
    fallback_hash: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        digest = parts[0]
        if not SHA256_RE.fullmatch(digest):
            raise JudgeError("invalid SHA-256 checksum format")
        if len(parts) == 1:
            fallback_hash = digest.lower()
            continue
        candidate_name = Path(parts[-1].lstrip("*")).name
        if candidate_name == artifact_name:
            return digest.lower()
    if fallback_hash:
        return fallback_hash
    raise JudgeError(f"checksum entry not found for {artifact_name}")


def write_sha256_sidecar(artifact_path: Path) -> Path:
    """sha256 sidecar 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        artifact_path (Path): 산출물 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.

    Returns:
        Path: 검증된 sha256 sidecar 경로입니다. 선택 항목이 없거나 찾지 못한 경우 None일 수 있습니다.
    """
    checksum_path = checksum_sidecar_path(artifact_path)
    checksum_path.write_text(
        f"{sha256_file(artifact_path)}  {artifact_path.name}\n",
        encoding="utf-8",
    )
    return checksum_path


def verify_sha256_text(artifact_path: Path, checksum_text: str) -> str:
    expected = parse_sha256_checksum(checksum_text, artifact_path.name)
    actual = sha256_file(artifact_path)
    if actual.lower() != expected.lower():
        raise JudgeError(
            f"checksum mismatch for {artifact_path.name}: expected {expected}, got {actual}"
        )
    return expected.lower()


def verify_sha256_sidecar(artifact_path: Path) -> str:
    """verify sha256 sidecar 파일을 안전한 경로에서 읽거나 쓰고 실패 상황을 호출자에게 전달합니다.

    Args:
        artifact_path (Path): 산출물 경로를 읽거나 쓸 때 기준으로 삼는 파일시스템 경로입니다.

    Returns:
        str: 호출자가 식별자, 경로, 메시지로 사용할 verify sha256 sidecar 문자열입니다.
    """
    checksum_path = checksum_sidecar_path(artifact_path)
    if not checksum_path.exists():
        raise JudgeError(f"missing checksum sidecar: {checksum_path.name}")
    return verify_sha256_text(artifact_path, checksum_path.read_text(encoding="utf-8"))
