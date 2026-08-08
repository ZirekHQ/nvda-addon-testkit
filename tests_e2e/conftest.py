"""End-to-end tests against a real NVDA. Windows only, never part of a bare pytest run."""

from __future__ import annotations

import re
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

collect_ignore_glob = [] if sys.platform == "win32" else ["test_*.py"]

#: A full --log-level=DEBUG NVDA startup on a GitHub windows runner has no audio
#: endpoint, no braille display and no interactive desktop, so NVDA logs ERROR
#: while initialising those. Those errors are the runner, not the add-on under
#: test, and asserting on them would make the first red CI run a false alarm.
#: Expect to tune this list after that first run: every allowlisted record is
#: reported as a warning, and the failure message quotes them all either way.
RUNNER_ENVIRONMENT_ERRORS = (
    r"nvwave|WASAPI|audio (?:device|output|session|endpoint)",
    r"synthDriver|synthesi[sz]|espeak|oneCore|SAPI",
    r"braille ?display|brailleDisplayDriver|brailleInput",
    r"UIAHandler|IAccessible|interactive desktop|desktop object",
)

_RUNNER_ENVIRONMENT = re.compile("|".join(RUNNER_ENVIRONMENT_ERRORS), re.IGNORECASE)


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


def check_no_unexpected_errors(client, *, since: int = 0) -> None:
    """nvda.log.assert_no_errors(), minus what a headless runner logs by itself."""
    environmental, unexpected = [], []
    for record in client.log.errors(since=since):
        target = environmental if _RUNNER_ENVIRONMENT.search(record.message) else unexpected
        target.append(record)

    listed = "\n".join(f"  {r}" for r in environmental) or "  (none)"
    if environmental:
        joined = "; ".join(str(r) for r in environmental)
        warnings.warn(
            f"ignored {len(environmental)} runner-environment error(s): {joined}",
            stacklevel=2,
        )
    if unexpected:
        raise AssertionError(
            f"NVDA logged {len(unexpected)} unexpected error(s):\n"
            + "\n".join(f"  {r}" for r in unexpected)
            + f"\n\nAlso logged, and allowlisted as runner-environment noise:\n{listed}"
        )


@pytest.fixture
def assert_no_unexpected_errors():
    return check_no_unexpected_errors
