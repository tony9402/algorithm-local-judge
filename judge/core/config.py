"""Shared configuration constants for the local judge."""

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
