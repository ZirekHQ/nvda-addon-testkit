"""Configuration from [tool.nvda-testkit] in pyproject.toml, plus CLI overrides.

tomllib is stdlib from 3.11, which is the floor -- no external TOML dependency.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

_KEY_MAP = {
    "nvda-channel": "channel",
    "addon-bundle": "addon_bundle",
    "modules": "modules",
    "allow-eval": "allow_eval",
    "timeout-scale": "timeout_scale",
    "keep-portable": "keep_portable",
    "out-dir": "out_dir",
    "timeout": "timeout",
    "fail-on-log-errors": "fail_on_log_errors",
    "ignore-log-errors": "ignore_log_errors",
    "verbose": "verbose",
}


@dataclass(frozen=True)
class TestkitSettings:
    channel: str = "stable"
    addon_bundle: str | None = None
    modules: tuple[str, ...] = ()
    allow_eval: bool = False
    timeout_scale: float = 1.0
    keep_portable: bool = False
    out_dir: Path = Path("testOutput")
    timeout: float = 10.0
    fail_on_log_errors: bool = False
    ignore_log_errors: tuple[str, ...] = ()
    verbose: bool = False


def _duration(field: str, value) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be a finite positive number, got {value!r}")
    return number


def _coerce(field: str, value):
    if field in ("modules", "ignore_log_errors"):
        return (value,) if isinstance(value, str) else tuple(value)
    if field == "out_dir":
        return Path(value)
    if field in ("timeout", "timeout_scale"):
        return _duration(field, value)
    if field in ("allow_eval", "keep_portable", "fail_on_log_errors", "verbose"):
        return bool(value)
    return value


def load_settings(
    pyproject: Path | None = None,
    overrides: dict | None = None,
) -> TestkitSettings:
    path = Path(pyproject) if pyproject is not None else Path("pyproject.toml")
    values: dict = {}

    if path.is_file():
        with path.open("rb") as handle:
            document = tomllib.load(handle)
        section = document.get("tool", {}).get("nvda-testkit", {})
        for key, value in section.items():
            field = _KEY_MAP.get(key)
            if field:
                values[field] = _coerce(field, value)

    for field, value in (overrides or {}).items():
        if value is not None:
            values[field] = _coerce(field, value)

    return cast(TestkitSettings, replace(TestkitSettings(), **values))
