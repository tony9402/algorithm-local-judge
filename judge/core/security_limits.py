"""Compatibility alias for the canonical :mod:`alj_core.security_limits` module."""

from __future__ import annotations

import sys

from alj_core import security_limits as _canonical

sys.modules[__name__] = _canonical
