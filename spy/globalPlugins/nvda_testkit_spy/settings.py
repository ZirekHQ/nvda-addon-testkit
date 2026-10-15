# coding: utf-8
"""The session environment the host hands the spy; absent means stay inert."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

TOKEN_VARIABLE = "NVDA_TESTKIT_TOKEN"
OUTDIR_VARIABLE = "NVDA_TESTKIT_OUTDIR"


@dataclass(frozen=True)
class Settings:
    token: str
    out_dir: str

    @staticmethod
    def from_environ(environ: Optional[Mapping[str, str]] = None) -> Optional["Settings"]:
        """Return the settings, or None unless both variables are set and non-empty."""
        source = os.environ if environ is None else environ
        token = source.get(TOKEN_VARIABLE)
        out_dir = source.get(OUTDIR_VARIABLE)
        if not token or not out_dir:
            return None
        return Settings(token=token, out_dir=out_dir)
