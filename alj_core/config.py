"""설정 도메인 로직과 파일시스템 변경 정책을 담당합니다.
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
