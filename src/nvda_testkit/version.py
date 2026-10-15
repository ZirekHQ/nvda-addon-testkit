"""NVDA version information as exposed to tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NvdaVersion:
    version: str
    api_version: str | None
    api_compat_to: str | None
    channel: str = "unknown"
