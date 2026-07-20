"""Compatibility alias for the canonical :mod:`alj_core.tool_compiler` module."""

from __future__ import annotations

import sys

from alj_core import tool_compiler as _canonical

sys.modules[__name__] = _canonical
