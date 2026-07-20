"""Compatibility alias for :mod:`alj_core.toolchains`."""

from __future__ import annotations

import sys

from alj_core import toolchains as _canonical

sys.modules[__name__] = _canonical
