#!/usr/bin/env python3
"""Zip the demo add-on into examples/demo-addon.nvda-addon."""

from __future__ import annotations

import zipfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
BUNDLE = SOURCE.parent / "demo-addon.nvda-addon"


def build() -> Path:
    files = sorted(
        path
        for path in SOURCE.rglob("*")
        if path.is_file()
        and path.name != "build.py"
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    )
    with zipfile.ZipFile(BUNDLE, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(SOURCE).as_posix())
    print(f"wrote {BUNDLE}")
    return BUNDLE


if __name__ == "__main__":
    build()
