"""Create a disposable portable NVDA and seed it for testing.

Portable rather than a system install: no admin rights, several NVDA versions
side by side, and cleanup is deleting a directory. The trade-off, accepted
deliberately, is that the secure/lock screen is out of reach.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ProvisionError, UnsupportedPlatformError

type IniValue = str | int | float | bool | list[Any] | tuple[Any, ...]
type IniTree = Mapping[str, IniValue | IniTree]

_NEEDS_QUOTES = frozenset(",#\"'=[]")
_TRIPLE_QUOTES = ("'" * 3, '"' * 3)

DEFAULT_CONFIG: IniTree = {
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


def _render_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    text = str(value)
    multiline = "\n" in text or "\r" in text
    if text and not multiline and text == text.strip() and not _NEEDS_QUOTES.intersection(text):
        return text
    if not multiline and '"' not in text:
        return f'"{text}"'
    if not multiline and "'" not in text:
        return f"'{text}'"
    for quote in _TRIPLE_QUOTES:
        if quote not in text and not text.endswith(quote[0]):
            return f"{quote}{text}{quote}"
    raise ProvisionError(f"Cannot render {text!r} as an nvda.ini value: no safe quoting exists.")


def _render_name(name: str) -> str:
    if "\n" in name or "\r" in name:
        raise ProvisionError(f"Cannot render {name!r} as an nvda.ini key: it has a newline.")
    return _render_scalar(name)


def _render_member(value: object) -> str:
    text = _render_scalar(value)
    if "\n" in text or "\r" in text:
        raise ProvisionError(
            f"Cannot render {value!r} as an nvda.ini list member: it has a newline."
        )
    return text


def _render_value(value: object) -> str:
    if isinstance(value, (list, tuple)):
        if len(value) == 1:
            return _render_member(value[0]) + ","
        return ", ".join(_render_member(item) for item in value) if value else ","
    return _render_scalar(value)


def _render_section(name: str, values: IniTree, depth: int) -> list[str]:
    brackets = "[" * depth
    closing = "]" * depth
    lines = [f"{brackets}{_render_name(name)}{closing}"]
    nested: list[str] = []
    for key, value in values.items():
        if isinstance(value, Mapping):
            nested.extend(_render_section(key, value, depth + 1))
        else:
            lines.append(f"{_render_name(key)} = {_render_value(value)}")
    return lines + nested


def _merge(base: IniTree, overrides: IniTree) -> IniTree:
    merged: dict[str, IniValue | IniTree] = {
        key: dict(value) if isinstance(value, Mapping) else value for key, value in base.items()
    }
    for key, value in overrides.items():
        current = merged.get(key)
        if isinstance(value, Mapping) and isinstance(current, Mapping):
            merged[key] = _merge(current, value)
        else:
            merged[key] = value
    return merged


def render_nvda_ini(overrides: IniTree | None = None) -> str:
    """Render an nvda.ini in ConfigObj's format.

    schemaVersion is deliberately omitted: NVDA fills in its own defaults for a
    partial config, which is more durable than pinning a number that changes
    every release.
    """
    config = _merge(DEFAULT_CONFIG, overrides or {})
    lines: list[str] = []
    for name, values in config.items():
        if not isinstance(values, Mapping):
            lines.append(f"{name} = {_render_value(values)}")
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


def seed_user_config(root: Path, overrides: IniTree | None = None) -> Path:
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
