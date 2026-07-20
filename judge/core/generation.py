"""Compatibility alias for the canonical :mod:`alj_core.generation` module."""

from __future__ import annotations

import sys

from alj_core import generation as _canonical

sys.modules[__name__] = _canonical
