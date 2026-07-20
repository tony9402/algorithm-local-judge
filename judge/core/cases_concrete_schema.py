"""Compatibility alias for the canonical :mod:`alj_core.cases_concrete_schema` module."""

from __future__ import annotations

import sys

from alj_core import cases_concrete_schema as _canonical

sys.modules[__name__] = _canonical
