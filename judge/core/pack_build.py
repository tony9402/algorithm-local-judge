"""Compatibility alias for the canonical :mod:`alj_core.pack_build` module."""

from __future__ import annotations

import sys

from alj_core import pack_build as _canonical

sys.modules[__name__] = _canonical
