"""Put the spy package on sys.path with NVDA stubbed, once per process."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SPY_GLOBAL_PLUGINS = REPO_ROOT / "spy" / "globalPlugins"

if str(SPY_GLOBAL_PLUGINS) not in sys.path:
    sys.path.insert(0, str(SPY_GLOBAL_PLUGINS))

from tests_spy import nvda_stubs  # noqa: E402

_STUBS = nvda_stubs.install()


@pytest.fixture(autouse=True)
def _fresh_config(monkeypatch):
    """A stub NVDA config no test can leave mutated for the next one."""
    fresh = nvda_stubs.FakeConfigManager(nvda_stubs.DEFAULT_CONFIG)
    monkeypatch.setattr(sys.modules["config"], "conf", fresh)


@pytest.fixture
def event_queue():
    """The fake NVDA main-thread queue, with auto-drain on by default."""
    queue = _STUBS["_eventQueue"]
    queue.pending.clear()
    queue.auto_drain = True
    return queue
