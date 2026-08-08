"""Work out which NVDA launcher to download for a given channel.

Stable and beta come from nvaccess's update-check endpoint, which returns
`key: value` lines and always reports the newest build regardless of the
version we claim to be running. Alpha has no such endpoint -- passing
versionType=alpha returns a 404 -- so it is resolved by scraping the snapshot
directory index.
"""

from __future__ import annotations

import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from .errors import LauncherResolutionError

CHANNELS: tuple[str, ...] = ("stable", "beta", "alpha")

_UPDATE_CHECK_URL = (
    "https://download.nvaccess.org/nvdaUpdateCheck"
    "?autoCheck=false&versionType={channel}&version=2019.1"
)
_SNAPSHOT_INDEX_URL = "https://download.nvaccess.org/snapshots/alpha/"
_RELEASE_URL = "https://download.nvaccess.org/releases/{version}/nvda_{version}.exe"

_SNAPSHOT_RE = re.compile(r"nvda_snapshot_alpha-(\d+),([0-9a-f]+)\.exe")
_PINNED_RE = re.compile(r"^\d{4}\.\d+(\.\d+)?(beta\d+|rc\d+)?$")

_USER_AGENT = "nvda-addon-testkit"


@dataclass(frozen=True)
class LauncherInfo:
    """Everything needed to fetch and verify one NVDA launcher.

    `sha1` is None for alpha snapshots and pinned versions, which publish no
    digest. Callers must treat None as "unverifiable", never as "verified".
    """

    channel: str
    version: str
    url: str
    sha1: str | None
    api_version: str | None
    api_compat_to: str | None


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _parse_update_check(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in body.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    return fields


def _resolve_released(channel: str, fetch: Callable[[str], bytes]) -> LauncherInfo:
    url = _UPDATE_CHECK_URL.format(channel=channel)
    fields = _parse_update_check(fetch(url).decode("utf-8", errors="replace"))
    launcher_url = fields.get("launcherUrl")
    if not launcher_url:
        raise LauncherResolutionError(
            f"The update-check endpoint returned no launcherUrl for channel {channel!r}. "
            f"Got fields: {sorted(fields)}"
        )
    return LauncherInfo(
        channel=channel,
        version=fields.get("version", "unknown"),
        url=launcher_url,
        sha1=fields.get("launcherHash"),
        api_version=fields.get("apiVersion"),
        api_compat_to=fields.get("apiCompatTo"),
    )


def _resolve_alpha(fetch: Callable[[str], bytes]) -> LauncherInfo:
    html = fetch(_SNAPSHOT_INDEX_URL).decode("utf-8", errors="replace")
    matches = _SNAPSHOT_RE.findall(html)
    if not matches:
        raise LauncherResolutionError(
            f"Found no alpha snapshot filenames at {_SNAPSHOT_INDEX_URL}. "
            "The directory layout may have changed."
        )
    revision, commit = max(matches, key=lambda pair: int(pair[0]))
    filename = f"nvda_snapshot_alpha-{revision},{commit}.exe"
    return LauncherInfo(
        channel="alpha",
        version=f"alpha-{revision},{commit}",
        url=_SNAPSHOT_INDEX_URL + filename,
        sha1=None,
        api_version=None,
        api_compat_to=None,
    )


def resolve_launcher(
    channel: str = "stable",
    *,
    fetch: Callable[[str], bytes] = fetch_url,
) -> LauncherInfo:
    """Resolve a channel name, or a pinned version like "2026.1.1", to a launcher."""
    if channel in ("stable", "beta"):
        return _resolve_released(channel, fetch)
    if channel == "alpha":
        return _resolve_alpha(fetch)
    if _PINNED_RE.match(channel):
        return LauncherInfo(
            channel="pinned",
            version=channel,
            url=_RELEASE_URL.format(version=channel),
            sha1=None,
            api_version=None,
            api_compat_to=None,
        )
    raise LauncherResolutionError(
        f"{channel!r} is not a known channel. Expected one of {CHANNELS} "
        "or a pinned version such as '2026.1.1'."
    )
