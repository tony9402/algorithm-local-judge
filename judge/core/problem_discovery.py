"""Compatibility alias for the canonical :mod:`alj_core.problem_discovery` module."""

from __future__ import annotations

import sys

from alj_core import problem_discovery as _canonical

sys.modules[__name__] = _canonical
