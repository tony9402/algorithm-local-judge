"""Compatibility alias for the canonical :mod:`alj_core.solution_expectations` module."""

from __future__ import annotations

import sys

from alj_core import solution_expectations as _canonical

sys.modules[__name__] = _canonical
