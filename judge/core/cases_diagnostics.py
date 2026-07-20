"""Compatibility alias for the canonical :mod:`alj_core.cases_diagnostics` module."""

from __future__ import annotations

import sys

from alj_core import cases_diagnostics as _canonical

sys.modules[__name__] = _canonical
