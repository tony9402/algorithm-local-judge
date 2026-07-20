"""Compatibility alias for the canonical :mod:`alj_core.manifest` module."""

from __future__ import annotations

import sys

from alj_core import manifest as _canonical

sys.modules[__name__] = _canonical
