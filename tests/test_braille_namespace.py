import threading

import pytest

from nvda_testkit.errors import WaitTimeout
from nvda_testkit.namespaces.braille import BrailleNamespace
from nvda_testkit.process import NvdaProcess
from nvda_testkit.rpcclient import RpcClient


@pytest.fixture
def braille(fake_nvda):
    proc = NvdaProcess(
        fake_nvda.argv, fake_nvda.out_dir, token=fake_nvda.token, env=fake_nvda.env, quit_via="rpc"
    )
    handshake = proc.start(timeout=20)
    rpc = RpcClient.from_handshake(handshake, token=fake_nvda.token)
    yield BrailleNamespace(rpc), rpc
    rpc.close()
    proc.kill()


def test_index_and_since_round_trip(braille):
    namespace, rpc = braille
    assert namespace.index() == 0
    rpc.call("braille_emit", "Edit  multi line")
    assert namespace.index() == 1
    assert namespace.since(0) == ["Edit  multi line"]


def test_last_returns_none_before_anything_is_written(braille):
    namespace, _ = braille
    assert namespace.last() is None


def test_wait_for_finds_a_later_write(braille):
    namespace, rpc = braille
    threading.Timer(0.2, lambda: rpc.call("braille_emit", "btn Install")).start()
    assert "Install" in namespace.wait_for("Install", timeout=10)


def test_wait_for_ignores_earlier_writes_by_default(braille):
    namespace, rpc = braille
    rpc.call("braille_emit", "old content")
    with pytest.raises(WaitTimeout):
        namespace.wait_for("old content", timeout=0.5)


def test_a_timeout_reports_what_was_on_the_display(braille):
    namespace, rpc = braille
    rpc.call("braille_emit", "something else entirely")
    with pytest.raises(WaitTimeout) as excinfo:
        namespace.wait_for("expected", timeout=0.5, since=0)
    assert "something else entirely" in str(excinfo.value)


def test_cell_count_round_trips(braille):
    namespace, _ = braille
    namespace.set_cell_count(80)
    assert namespace.cell_count() == 80
