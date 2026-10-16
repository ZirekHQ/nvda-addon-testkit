"""Fetch NVDA launchers, verify them against nvaccess's published SHA-1, and
cache them on disk.

A launcher whose digest does not match is deleted, not quarantined.
Launchers with no published digest are pinned trust-on-first-use: the SHA-256
and SHA-1 of the first download are stored beside it and re-checked on every
cache hit, so a cache entry swapped afterwards is detected and re-fetched.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

from .errors import HashMismatchError
from .resolve import LauncherInfo, fetch_url
from .settings import cache_dir_from_environment

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
_SHA1_SUFFIX = ".sha1"
_SHA256_SUFFIX = ".sha256"


def default_cache_dir() -> Path:
    return cache_dir_from_environment() or Path.home() / ".cache" / "nvda-testkit"


def _digest_file(path: Path, algorithm: str) -> str:
    # nvaccess publishes SHA-1 only; it is a transport check, not a security boundary.
    digest = hashlib.new(algorithm, usedforsecurity=algorithm != "sha1")
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha1_file(path: Path) -> str:
    return _digest_file(path, "sha1")


def sha256_file(path: Path) -> str:
    return _digest_file(path, "sha256")


def _cache_name(info: LauncherInfo) -> str:
    stem = info.sha1 or f"{info.channel}-{info.version}"
    return _UNSAFE.sub("_", stem) + ".exe"


def _read_note(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii").strip().lower() or None
    except (OSError, UnicodeDecodeError):
        return None


def _cached_is_trusted(target: Path, info: LauncherInfo) -> bool:
    if info.sha1 is not None:
        return sha1_file(target) == info.sha1.lower()
    pinned_256 = _read_note(target.with_suffix(_SHA256_SUFFIX))
    if pinned_256 is not None:
        return sha256_file(target) == pinned_256
    pinned_1 = _read_note(target.with_suffix(_SHA1_SUFFIX))
    return pinned_1 is not None and sha1_file(target) == pinned_1


def _discard(target: Path) -> None:
    for path in (target, target.with_suffix(_SHA1_SUFFIX), target.with_suffix(_SHA256_SUFFIX)):
        path.unlink(missing_ok=True)


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
        if _cached_is_trusted(target, info):
            return target
        _discard(target)

    payload = fetch(info.url)
    descriptor, partial_name = tempfile.mkstemp(dir=cache_dir, prefix=target.stem, suffix=".part")
    partial = Path(partial_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
        actual = sha1_file(partial)
        if info.sha1 is not None and actual != info.sha1.lower():
            raise HashMismatchError(expected=info.sha1, actual=actual, path=str(target))
        os.replace(partial, target)
    finally:
        with contextlib.suppress(OSError):
            partial.unlink(missing_ok=True)
    if info.sha1 is None:
        target.with_suffix(_SHA1_SUFFIX).write_text(actual + "\n", encoding="ascii")
        target.with_suffix(_SHA256_SUFFIX).write_text(sha256_file(target) + "\n", encoding="ascii")
    return target
