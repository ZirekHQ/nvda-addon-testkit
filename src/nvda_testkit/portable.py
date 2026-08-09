"""Create a disposable portable NVDA and seed it for testing.

Portable rather than a system install: no admin rights, several NVDA versions
side by side, and cleanup is deleting a directory. The trade-off, accepted
deliberately, is that the secure/lock screen is out of reach.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ProvisionError, UnsupportedPlatformError

#: Settings applied to every portable copy the kit creates. Each one removes
#: something that would either block a headless run or add wall-clock time.
DEFAULT_CONFIG: dict[str, Any] = {
    "general": {
        "showWelcomeDialogAtStartup": False,
        "saveConfigurationOnExit": False,
        "askToExit": False,
        "playStartAndExitSounds": False,
    },
    "update": {
        "autoCheck": False,
        "startupNotification": False,
        "allowUsageStats": False,
        # NVDA only skips AskAllowUsageStatsDialog once this is set; setting
        # allowUsageStats alone still shows the blocking first-run prompt.
        "askedAllowUsageStats": True,
    },
    "braille": {
        "display": "noBraille",
    },
    "speechViewer": {
        "showSpeechViewerAtStartup": False,
    },
}


@dataclass(frozen=True)
class PortableNvda:
    root: Path
    exe: Path
    user_config: Path
    addons_dir: Path


def _render_section(name: str, values: dict[str, Any], depth: int) -> list[str]:
    brackets = "[" * depth
    closing = "]" * depth
    lines = [f"{brackets}{name}{closing}"]
    nested: list[str] = []
    for key, value in values.items():
        if isinstance(value, dict):
            nested.extend(_render_section(key, value, depth + 1))
        else:
            lines.append(f"{key} = {value}")
    return lines + nested


def _merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = {key: dict(value) if isinstance(value, dict) else value for key, value in base.items()}
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def render_nvda_ini(overrides: dict[str, Any] | None = None) -> str:
    """Render an nvda.ini in ConfigObj's format.

    schemaVersion is deliberately omitted: NVDA fills in its own defaults for a
    partial config, which is more durable than pinning a number that changes
    every release.
    """
    config = _merge(DEFAULT_CONFIG, overrides or {})
    lines: list[str] = []
    for name, values in config.items():
        if not isinstance(values, dict):
            lines.append(f"{name} = {values}")
            continue
        lines.extend(_render_section(name, values, depth=1))
    return "\n".join(lines) + "\n"


def extract_addon(bundle: Path, dest_dir: Path) -> None:
    """Unzip a .nvda-addon into dest_dir, refusing entries that escape it."""
    bundle = Path(bundle)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    resolved_dest = dest_dir.resolve()

    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        for name in names:
            target = (dest_dir / name).resolve()
            if not target.is_relative_to(resolved_dest):
                raise ProvisionError(
                    f"Entry {name!r} in {bundle} escapes the destination directory."
                )
        if "manifest.ini" not in names:
            raise ProvisionError(f"{bundle} has no manifest.ini; it is not an NVDA add-on bundle.")
        archive.extractall(dest_dir)


def seed_user_config(root: Path, overrides: dict[str, Any] | None = None) -> Path:
    root = Path(root)
    user_config = root / "userConfig"
    (user_config / "addons").mkdir(parents=True, exist_ok=True)
    (user_config / "nvda.ini").write_text(render_nvda_ini(overrides), encoding="utf-8")
    return user_config


def create_portable(launcher: Path, dest: Path, *, timeout: float = 300) -> PortableNvda:
    """Run the launcher to produce a portable copy at `dest`."""
    if sys.platform != "win32":
        raise UnsupportedPlatformError(
            "Creating a portable NVDA copy needs a real Windows host. "
            "Host-side logic is testable on Linux; this step is not."
        )
    launcher = Path(launcher)
    dest = Path(dest)
    if not launcher.is_file():
        raise ProvisionError(f"Launcher not found: {launcher}")

    try:
        completed = subprocess.run(
            [str(launcher), "--create-portable-silent", f"--portable-path={dest}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        raise ProvisionError(
            f"Creating a portable copy timed out after {timeout}s. Launcher: {launcher}\n"
            f"stdout so far: {expired.stdout!r}\nstderr so far: {expired.stderr!r}"
        ) from expired

    exe = dest / "nvda.exe"
    if completed.returncode != 0 or not exe.is_file():
        raise ProvisionError(
            f"Creating a portable copy failed (exit {completed.returncode}).\n"
            f"stdout: {completed.stdout.strip()}\n"
            f"stderr: {completed.stderr.strip()}"
        )

    user_config = seed_user_config(dest)
    return PortableNvda(
        root=dest,
        exe=exe,
        user_config=user_config,
        addons_dir=user_config / "addons",
    )
