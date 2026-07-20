"""Compatibility alias for the canonical :mod:`alj_core.utils.fs` module."""

from __future__ import annotations

import sys

from alj_core.utils import fs as _canonical

sys.modules[__name__] = _canonical
