import pytest

from nvda_testkit.client import NvdaClient, NvdaVersion
from nvda_testkit.errors import TestkitError
from nvda_testkit.process import NvdaProcess
from nvda_testkit.rpcclient import RpcClient
from nvda_testkit.settings import TestkitSettings


@pytest.fixture
def client(fake_nvda):
    proc = NvdaProcess(
        fake_nvda.argv, fake_nvda.out_dir, token=fake_nvda.token, env=fake_nvda.env, quit_via="rpc"
    )
    handshake = proc.start(timeout=20)
    rpc = RpcClient.from_handshake(handshake, token=fake_nvda.token)
    instance = NvdaClient(proc, rpc)
    yield instance
    instance.close()
    proc.kill()


def test_every_namespace_is_present(client):
    for name in ("speech", "braille", "keys", "config", "log"):
        assert hasattr(client, name), f"nvda.{name} missing"


def test_version_reports_what_the_handshake_said(client):
    version = client.version
    assert isinstance(version, NvdaVersion)
    assert version.version == "2026.1.1"
    assert version.api_compat_to == "2026.1.0"


def test_wait_until_idle_returns(client):
    client.wait_until_idle(timeout=5)


def test_reset_clears_every_cache(client):
    client.speech.speak("noise")
    client.log._rpc.call("log_emit", "INFO", "noise")
    client.braille._rpc.call("braille_emit", "noise")
    assert client.speech.index() > 0

    client.reset()

    assert client.speech.index() == 0
    assert client.braille.index() == 0
    assert client.log.index() == 0


def test_reset_restores_config_to_the_baseline(client):
    client.config.set(("speech", "synth"), "changed")
    client.reset()
    assert client.config.get(("speech", "synth")) == "espeak"


def test_eval_is_refused_unless_explicitly_allowed(client):
    with pytest.raises(TestkitError, match="--nvda-allow-eval"):
        client.eval("1 + 1")


def test_eval_works_when_allowed(fake_nvda):
    proc = NvdaProcess(
        fake_nvda.argv, fake_nvda.out_dir, token=fake_nvda.token, env=fake_nvda.env, quit_via="rpc"
    )
    handshake = proc.start(timeout=20)
    rpc = RpcClient.from_handshake(handshake, token=fake_nvda.token)
    try:
        permissive = NvdaClient(proc, rpc, settings=TestkitSettings(allow_eval=True))
        assert permissive.eval("2 + 2") == 4
    finally:
        proc.kill()
