"""Guards around the start-and-connect sequence in provision_fake/provision."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nvda_testkit import provisioning
from nvda_testkit.settings import TestkitSettings

FAKE = Path(__file__).parent / "fake_nvda.py"


def test_a_malformed_handshake_does_not_leak_the_process(monkeypatch):
    """A handshake payload that is valid JSON but missing a required key must
    not leave the FakeNvda subprocess running: process.start() itself raises
    (Handshake.from_payload -> KeyError) without calling kill(), so the guard
    around the whole start-and-connect sequence in provision_fake() is what
    has to catch it.
    """
    monkeypatch.setenv("FAKE_NVDA_SCRIPT", json.dumps({"bad_handshake": True}))

    created: list[provisioning.NvdaProcess] = []
    real_process_class = provisioning.NvdaProcess

    class RecordingProcess(real_process_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(provisioning, "NvdaProcess", RecordingProcess)

    with pytest.raises(KeyError):
        provisioning.provision_fake(TestkitSettings(), FAKE)

    assert created, "expected an NvdaProcess to have been constructed"
    assert created[0].is_running is False, "the leaked subprocess must be killed on failure"
