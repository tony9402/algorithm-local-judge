"""config 모듈의 공개 동작을 설명합니다.

Args:
    없음

Returns:
    None: 처리 결과를 반환합니다.
"""

import re

PROTOCOL_VERSION = 1
COMPILE_FLAGS = ["-std=c++17", "-O2", "-pipe"]
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
FORBIDDEN_METADATA_KEYS = {
    "externalId",
    "externalUrl",
    "externalPlatform",
    "platform",
}
