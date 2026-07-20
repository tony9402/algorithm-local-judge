"""Compatibility alias for :mod:`alj_core.toolchain_manifest`."""

from __future__ import annotations

import sys

from alj_core import toolchain_manifest as _canonical

sys.modules[__name__] = _canonical
