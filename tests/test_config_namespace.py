import pytest

from nvda_testkit.namespaces.config import ConfigNamespace
from nvda_testkit.process import NvdaProcess
from nvda_testkit.rpcclient import RpcClient


@pytest.fixture
def config(fake_nvda):
    proc = NvdaProcess(
        fake_nvda.argv, fake_nvda.out_dir, token=fake_nvda.token, env=fake_nvda.env, quit_via="rpc"
    )
    handshake = proc.start(timeout=20)
    rpc = RpcClient.from_handshake(handshake, token=fake_nvda.token)
    yield ConfigNamespace(rpc)
    rpc.close()
    proc.kill()


def test_get_and_set_round_trip(config):
    assert config.get(("speech", "synth")) == "espeak"
    config.set(("speech", "synth"), "oneCore")
    assert config.get(("speech", "synth")) == "oneCore"


def test_a_string_path_is_accepted_as_a_single_key(config):
    config.set("topLevel", 7)
    assert config.get("topLevel") == 7


def test_snapshot_and_restore_undo_changes(config):
    snapshot = config.snapshot()
    config.set(("speech", "synth"), "changed")
    config.restore(snapshot)
    assert config.get(("speech", "synth")) == "espeak"
