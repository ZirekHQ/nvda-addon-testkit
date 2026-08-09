"""Locate the spy add-on bundle shipped inside the wheel."""

from __future__ import annotations

from pathlib import Path

from .errors import ProvisionError

BUNDLE_NAME = "nvda-testkit-spy.nvda-addon"


def spy_bundle_path() -> Path:
    bundle = Path(__file__).parent / "_spy" / BUNDLE_NAME
    return bundle


def require_spy_bundle() -> Path:
    bundle = spy_bundle_path()
    if not bundle.is_file():
        raise ProvisionError(
            f"The spy add-on bundle is missing at {bundle}. "
            "In a source checkout, run: python tools/build_spy.py"
        )
    return bundle
