"""Shared fixtures. The fake_nvda fixture is how every host-side test that
needs a running "NVDA" gets one, on any platform."""

from __future__ import annotations

import json
import secrets
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

FAKE_NVDA = Path(__file__).parent / "fake_nvda.py"


@dataclass
class FakeNvdaHandle:
    """Everything a test needs to point NvdaProcess at the double."""

    out_dir: Path
    token: str
    knobs: dict = field(default_factory=dict)

    @property
    def argv(self) -> list[str]:
        return [sys.executable, str(FAKE_NVDA)]

    @property
    def env(self) -> dict[str, str]:
        environment = {
            "NVDA_TESTKIT_TOKEN": self.token,
            "NVDA_TESTKIT_OUTDIR": str(self.out_dir),
        }
        if self.knobs:
            environment["FAKE_NVDA_SCRIPT"] = json.dumps(self.knobs)
        return environment

    def script(self, **knobs) -> FakeNvdaHandle:
        self.knobs.update(knobs)
        return self


@pytest.fixture
def fake_nvda(tmp_path):
    handle = FakeNvdaHandle(out_dir=tmp_path / "out", token=secrets.token_hex(16))
    handle.out_dir.mkdir(parents=True, exist_ok=True)
    yield handle
    # Sweep up anything a failing test left running.
    subprocess.run([sys.executable, "-c", "pass"], check=False, capture_output=True)
