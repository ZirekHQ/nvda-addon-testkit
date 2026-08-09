import pytest

from nvda_testkit.namespaces.log import LogNamespace, LogRecord
from nvda_testkit.process import NvdaProcess
from nvda_testkit.rpcclient import RpcClient


@pytest.fixture
def log(fake_nvda):
    proc = NvdaProcess(
        fake_nvda.argv, fake_nvda.out_dir, token=fake_nvda.token, env=fake_nvda.env, quit_via="rpc"
    )
    handshake = proc.start(timeout=20)
    rpc = RpcClient.from_handshake(handshake, token=fake_nvda.token)
    yield LogNamespace(rpc), rpc
    rpc.close()
    proc.kill()


def _emit(rpc, level, message):
    rpc.call("log_emit", level, message)


def test_records_parse_into_dataclasses(log):
    namespace, rpc = log
    _emit(rpc, "INFO", "started")
    (record,) = namespace.all()
    assert isinstance(record, LogRecord)
    assert record.level == "INFO"
    assert record.message == "started"


def test_assert_no_errors_passes_on_a_clean_log(log):
    namespace, rpc = log
    _emit(rpc, "INFO", "all fine")
    _emit(rpc, "DEBUG", "chatter")
    namespace.assert_no_errors()


def test_assert_no_errors_fails_and_quotes_every_offender(log):
    namespace, rpc = log
    _emit(rpc, "ERROR", "first thing broke")
    _emit(rpc, "INFO", "unrelated")
    _emit(rpc, "CRITICAL", "second thing broke")
    with pytest.raises(AssertionError) as excinfo:
        namespace.assert_no_errors()
    message = str(excinfo.value)
    assert "first thing broke" in message
    assert "second thing broke" in message
    assert "unrelated" not in message


def test_assert_no_warnings_is_stricter_than_assert_no_errors(log):
    namespace, rpc = log
    _emit(rpc, "WARNING", "deprecated call")
    namespace.assert_no_errors()
    with pytest.raises(AssertionError, match="deprecated call"):
        namespace.assert_no_warnings()


def test_since_lets_a_test_ignore_startup_noise(log):
    namespace, rpc = log
    _emit(rpc, "ERROR", "an error from before this test")
    boundary = namespace.index()
    _emit(rpc, "INFO", "clean from here")
    namespace.assert_no_errors(since=boundary)


def test_wait_for_finds_a_later_record(log):
    import threading

    namespace, rpc = log
    threading.Timer(0.2, lambda: _emit(rpc, "INFO", "voice loaded ok")).start()
    found = namespace.wait_for("voice loaded", timeout=10)
    assert found.message == "voice loaded ok"
