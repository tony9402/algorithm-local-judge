"""Compatibility alias for the canonical :mod:`alj_core.submission_cases` module."""

from __future__ import annotations

import sys

from alj_core import submission_cases as _canonical

sys.modules[__name__] = _canonical
