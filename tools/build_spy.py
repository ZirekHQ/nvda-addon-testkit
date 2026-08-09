#!/usr/bin/env python3
"""Zip spy/ into a .nvda-addon and drop it where the wheel will pick it up."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPY_DIR = REPO_ROOT / "spy"
OUT_DIR = REPO_ROOT / "src" / "nvda_testkit" / "_spy"
BUNDLE_NAME = "nvda-testkit-spy.nvda-addon"

_SKIP_DIRS = {"__pycache__"}
_SKIP_SUFFIXES = {".pyc", ".pyo"}


def build() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "__init__.py").write_text(
        '"""Built spy add-on bundle, produced by tools/build_spy.py."""\n',
        encoding="utf-8",
    )
    bundle = OUT_DIR / BUNDLE_NAME

    manifest = SPY_DIR / "manifest.ini"
    if not manifest.is_file():
        raise SystemExit(f"missing {manifest}")

    paths = sorted(
        path
        for path in SPY_DIR.rglob("*")
        if path.is_file()
        and path.suffix not in _SKIP_SUFFIXES
        and not _SKIP_DIRS.intersection(path.parts)
    )
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, path.relative_to(SPY_DIR).as_posix())

    print(f"wrote {bundle} ({bundle.stat().st_size} bytes, {len(paths)} entries)")
    return bundle


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
