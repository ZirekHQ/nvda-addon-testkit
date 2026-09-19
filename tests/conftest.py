"""Shared fixtures. The fake_nvda fixture is how every host-side test that
needs a running "NVDA" gets one, on any platform."""

from __future__ import annotations

import contextlib
import json
import secrets
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from nvda_testkit.client import NvdaClient
from nvda_testkit.dsl import Nvda
from nvda_testkit.process import NvdaProcess
from nvda_testkit.rpcclient import RpcClient
from nvda_testkit.settings import TestkitSettings

pytest_plugins = ["pytester"]

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
    """Config for a FakeNvda; it does not start one.

    Whoever launches the process owns killing it -- NvdaProcess from Task 6
    onward, or the `spawned` fixture in test_fake_nvda.py.
    """
    handle = FakeNvdaHandle(out_dir=tmp_path / "out", token=secrets.token_hex(16))
    handle.out_dir.mkdir(parents=True, exist_ok=True)
    return handle


@pytest.fixture
def make_client(fake_nvda):
    """Factory for a NvdaClient on the FakeNvda double."""
    started = []

    def build(**settings) -> NvdaClient:
        proc = NvdaProcess(
            fake_nvda.argv,
            fake_nvda.out_dir,
            token=fake_nvda.token,
            env=fake_nvda.env,
            quit_via="rpc",
        )
        rpc = RpcClient.from_handshake(proc.start(timeout=20), token=fake_nvda.token)
        client = NvdaClient(proc, rpc, settings=TestkitSettings(**settings))
        started.append((client, proc))
        return client

    yield build
    for client, proc in started:
        with contextlib.suppress(Exception):
            client.close()
        proc.kill()


@pytest.fixture
def make_dsl(make_client):
    def build(**settings) -> Nvda:
        return Nvda(make_client(**settings))

    return build
