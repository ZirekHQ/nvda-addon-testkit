import pytest

from nvda_testkit.errors import RpcError
from nvda_testkit.namespaces.keys import KeysNamespace
from nvda_testkit.process import NvdaProcess
from nvda_testkit.rpcclient import RpcClient


@pytest.fixture
def keys(fake_nvda):
    proc = NvdaProcess(
        fake_nvda.argv, fake_nvda.out_dir, token=fake_nvda.token, env=fake_nvda.env, quit_via="rpc"
    )
    handshake = proc.start(timeout=20)
    rpc = RpcClient.from_handshake(handshake, token=fake_nvda.token)
    yield KeysNamespace(rpc)
    rpc.close()
    proc.kill()


def test_a_press_is_recorded(keys):
    keys.press("NVDA+n")
    assert [entry["gesture"] for entry in keys.sent()] == ["NVDA+n"]


def test_press_all_sends_in_order(keys):
    keys.press_all("downArrow", "downArrow", "enter")
    assert [entry["gesture"] for entry in keys.sent()] == ["downArrow", "downArrow", "enter"]


def test_type_text_sends_named_gestures_for_whitespace(keys):
    keys.type_text("hi there")
    assert [entry["gesture"] for entry in keys.sent()] == [*list("hi"), "space", *list("there")]


def test_an_unknown_gesture_surfaces_as_an_rpc_error_naming_the_gesture(keys):
    with pytest.raises(RpcError, match="notakey"):
        keys.press("NVDA+notakey")
