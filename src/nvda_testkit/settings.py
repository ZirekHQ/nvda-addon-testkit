"""Configuration from [tool.nvda-testkit] in pyproject.toml, plus CLI overrides.

tomllib is stdlib, so there is no external TOML dependency.
"""

from __future__ import annotations

import math
import os
import tomllib
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import SettingsError

_KEY_MAP = {
    "nvda-channel": "channel",
    "addon-bundle": "addon_bundle",
    "modules": "modules",
    "allow-eval": "allow_eval",
    "timeout-scale": "timeout_scale",
    "keep-portable": "keep_portable",
    "out-dir": "out_dir",
    "cache-dir": "cache_dir",
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
    cache_dir: Path | None = None
    timeout: float = 10.0
    fail_on_log_errors: bool = False
    ignore_log_errors: tuple[str, ...] = ()
    verbose: bool = False


_TRUE = frozenset({"true", "1", "yes", "on"})
_FALSE = frozenset({"false", "0", "no", "off"})
_TUPLE_FIELDS = frozenset({"modules", "ignore_log_errors"})
_BOOL_FIELDS = frozenset({"allow_eval", "keep_portable", "fail_on_log_errors", "verbose"})
_PATH_FIELDS = frozenset({"out_dir", "cache_dir"})


def _duration(field: str, value: object) -> float:
    try:
        number = float(str(value))
    except ValueError:
        raise SettingsError(f"{field} must be a finite positive number, got {value!r}") from None
    if not math.isfinite(number) or number <= 0:
        raise SettingsError(f"{field} must be a finite positive number, got {value!r}")
    return number


def _boolean(field: str, value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in _TRUE | _FALSE:
        return value.strip().lower() in _TRUE
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise SettingsError(f"{field} must be a boolean, got {value!r}")


def _strings(field: str, value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise SettingsError(f"{field} must be a string or a list of strings, got {value!r}")


def _coerce(field: str, value: object) -> object:
    if field in _TUPLE_FIELDS:
        return _strings(field, value)
    if field in _PATH_FIELDS:
        if not isinstance(value, (str, os.PathLike)):
            raise SettingsError(f"{field} must be a path string, got {value!r}")
        return Path(value)
    if field in ("timeout", "timeout_scale"):
        return _duration(field, value)
    if field in _BOOL_FIELDS:
        return _boolean(field, value)
    return value


def _cache_dir_from(environ: Mapping[str, str]) -> Path | None:
    override = environ.get("NVDA_TESTKIT_CACHE")
    return Path(override) if override else None


def cache_dir_from_environment() -> Path | None:
    """The launcher cache location named by NVDA_TESTKIT_CACHE, if set."""
    return _cache_dir_from(os.environ)


def _values_from_pyproject(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as handle:
        section = tomllib.load(handle).get("tool", {}).get("nvda-testkit", {})
    values: dict[str, Any] = {}
    for key, value in section.items():
        field = _KEY_MAP.get(key)
        if field is None:
            warnings.warn(
                f"nvda-testkit: unknown key {key!r} under [tool.nvda-testkit] is ignored.",
                stacklevel=3,
            )
            continue
        values[field] = _coerce(field, value)
    return values


def load_settings(
    pyproject: Path | None = None,
    overrides: Mapping[str, object] | None = None,
    environ: Mapping[str, str] | None = None,
) -> TestkitSettings:
    path = Path(pyproject) if pyproject is not None else Path("pyproject.toml")
    values = _values_from_pyproject(path)

    for field, value in (overrides or {}).items():
        if value is not None:
            values[field] = _coerce(field, value)

    if "cache_dir" not in values:
        from_env = _cache_dir_from(os.environ if environ is None else environ)
        if from_env is not None:
            values["cache_dir"] = from_env

    return TestkitSettings(**values)
