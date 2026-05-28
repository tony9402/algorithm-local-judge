"""problem_install_policy 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""
from __future__ import annotations

PACK_INSTALL_POLICY = (
    ".aljpack release assets are preferred; source archive fallback is used only when "
    "no suitable pack asset is available."
)
PACK_INSTALL_TRUST_WARNING = (
    "Only install problem packs from repositories or files you trust; problem tools run locally."
)
SOURCE_INSTALL_TRUST_WARNING = (
    "Only install source packages from repositories you trust; problem tools run locally."
)
PACK_ASSET_NAME_PATTERN = "<pack-id>-<version>-<platform-id>.aljpack"


__all__ = [
    "PACK_ASSET_NAME_PATTERN",
    "PACK_INSTALL_POLICY",
    "PACK_INSTALL_TRUST_WARNING",
    "SOURCE_INSTALL_TRUST_WARNING",
]
