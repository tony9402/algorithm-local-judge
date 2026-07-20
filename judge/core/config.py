"""Compatibility alias for the canonical :mod:`alj_core.config` module."""

from __future__ import annotations

import sys

from alj_core import config as _canonical

sys.modules[__name__] = _canonical
