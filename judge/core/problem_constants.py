"""Compatibility alias for the canonical :mod:`alj_core.problem_constants` module."""

from __future__ import annotations

import sys

from alj_core import problem_constants as _canonical

sys.modules[__name__] = _canonical
