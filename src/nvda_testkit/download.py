"""Fetch NVDA launchers, verify them against nvaccess's published SHA-1, and
cache them on disk.

The digest check is not decoration: this code downloads an executable and then
runs it. A launcher whose digest does not match is deleted, not quarantined.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable
from pathlib import Path

from .errors import HashMismatchError
from .resolve import LauncherInfo, fetch_url

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def default_cache_dir() -> Path:
    override = os.environ.get("NVDA_TESTKIT_CACHE")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "nvda-testkit"


def sha1_file(path: Path) -> str:
    digest = hashlib.sha1()  # NOSONAR -- nvaccess publishes SHA-1; matches NVDA's own updater
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_name(info: LauncherInfo) -> str:
    stem = info.sha1 or f"{info.channel}-{info.version}"
    return _UNSAFE.sub("_", stem) + ".exe"


def ensure_launcher(
    info: LauncherInfo,
    cache_dir: Path | None = None,
    *,
    fetch: Callable[[str], bytes] = fetch_url,
) -> Path:
    """Return a path to a launcher for `info`, downloading it if necessary."""
    cache_dir = Path(cache_dir) if cache_dir is not None else default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / _cache_name(info)

    if target.exists():
        if info.sha1 is None or sha1_file(target) == info.sha1:
            return target
        target.unlink()

    partial = target.with_suffix(".part")
    payload = fetch(info.url)
    partial.write_bytes(payload)

    actual = sha1_file(partial)
    if info.sha1 is not None and actual != info.sha1:
        partial.unlink()
        raise HashMismatchError(expected=info.sha1, actual=actual, path=str(target))

    os.replace(partial, target)
    if info.sha1 is None:
        # Nothing to check against, so record what we actually got. This ends up
        # in the artifact bundle, which is the only way to tell after the fact
        # which alpha build a failure came from.
        target.with_suffix(".sha1").write_text(actual + "\n", encoding="ascii")
    return target
