import pytest

from nvda_testkit.errors import WaitTimeout
from nvda_testkit.namespaces.speech import SpeechNamespace
from nvda_testkit.process import NvdaProcess
from nvda_testkit.rpcclient import RpcClient


@pytest.fixture
def speech(fake_nvda):
    proc = NvdaProcess(
        fake_nvda.argv, fake_nvda.out_dir, token=fake_nvda.token, env=fake_nvda.env, quit_via="rpc"
    )
    handshake = proc.start(timeout=20)
    rpc = RpcClient.from_handshake(handshake, token=fake_nvda.token)
    yield SpeechNamespace(rpc), rpc
    rpc.close()
    proc.kill()


def _emit(rpc, text):
    rpc.call("speech_emit", [{"kind": "text", "text": text}])


def test_index_starts_at_zero_and_advances(speech):
    namespace, rpc = speech
    assert namespace.index() == 0
    _emit(rpc, "hello")
    assert namespace.index() == 1


def test_since_parses_into_speech_sequences(speech):
    namespace, rpc = speech
    _emit(rpc, "hello")
    (sequence,) = namespace.since(0)
    assert sequence.text == "hello"


def test_last_returns_none_when_nothing_has_been_said(speech):
    namespace, _ = speech
    assert namespace.last() is None


def test_last_returns_the_most_recent(speech):
    namespace, rpc = speech
    _emit(rpc, "first")
    _emit(rpc, "second")
    assert namespace.last().text == "second"


def test_wait_for_returns_as_soon_as_the_pattern_appears(speech):
    namespace, rpc = speech
    import threading

    threading.Timer(0.2, lambda: _emit(rpc, "the voice is ready")).start()
    found = namespace.wait_for("voice is ready", timeout=10)
    assert "voice is ready" in found.text


def test_wait_for_only_considers_speech_after_the_call_began(speech):
    namespace, rpc = speech
    _emit(rpc, "stale speech from an earlier test")
    with pytest.raises(WaitTimeout):
        namespace.wait_for("stale speech", timeout=0.5)


def test_wait_for_can_be_told_to_look_further_back(speech):
    namespace, rpc = speech
    _emit(rpc, "earlier line")
    found = namespace.wait_for("earlier line", timeout=5, since=0)
    assert found.text == "earlier line"


def test_a_timeout_reports_what_was_actually_spoken(speech):
    namespace, rpc = speech
    _emit(rpc, "something entirely different")
    with pytest.raises(WaitTimeout) as excinfo:
        namespace.wait_for("expected phrase", timeout=0.5, since=0)
    message = str(excinfo.value)
    assert "expected phrase" in message
    assert "something entirely different" in message


def test_clear_resets_the_cursor(speech):
    namespace, rpc = speech
    _emit(rpc, "noise")
    namespace.clear()
    assert namespace.index() == 0
    assert namespace.all() == []
