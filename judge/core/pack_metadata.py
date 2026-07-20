"""Compatibility alias for the canonical :mod:`alj_core.pack_metadata` module."""

from __future__ import annotations

import sys

from alj_core import pack_metadata as _canonical

sys.modules[__name__] = _canonical
