"""Compatibility alias for the canonical :mod:`alj_core.solution_validation` module."""

from __future__ import annotations

import sys

from alj_core import solution_validation as _canonical

sys.modules[__name__] = _canonical
