"""Compatibility alias for the canonical :mod:`alj_core.pack_install` module."""

from __future__ import annotations

import sys

from alj_core import pack_install as _canonical

sys.modules[__name__] = _canonical
