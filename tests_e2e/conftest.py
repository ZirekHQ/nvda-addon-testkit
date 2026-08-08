"""End-to-end tests against a real NVDA. Windows only, never part of a bare pytest run."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

collect_ignore_glob = [] if sys.platform == "win32" else ["test_*.py"]


@pytest.fixture(scope="session", autouse=True)
def built_demo_addon():
    """Build the demo bundle before the session, so addon_bundle can find it."""
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "examples" / "demo-addon" / "build.py")],
        check=True,
    )
    return REPO_ROOT / "examples" / "demo-addon.nvda-addon"


@pytest.fixture(scope="session")
def addon_bundle(built_demo_addon) -> Path:
    """Override the plugin's fixture: the kit's own e2e suite has a known bundle."""
    return built_demo_addon
