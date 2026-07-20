"""Compatibility alias for the canonical :mod:`alj_core.submission_warmup` module."""

from __future__ import annotations

import sys

from alj_core import submission_warmup as _canonical

sys.modules[__name__] = _canonical
