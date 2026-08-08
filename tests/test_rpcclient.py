import time
import xmlrpc.client

import pytest

from nvda_testkit.errors import AuthError, RpcError, WaitTimeout
from nvda_testkit.process import NvdaProcess
from nvda_testkit.rpcclient import RpcClient


@pytest.fixture
def client(fake_nvda):
    proc = NvdaProcess(
        fake_nvda.argv,
        fake_nvda.out_dir,
        token=fake_nvda.token,
        env=fake_nvda.env,
        quit_via="rpc",
    )
    handshake = proc.start(timeout=20)
    rpc = RpcClient.from_handshake(handshake, token=fake_nvda.token)
    yield rpc
    rpc.close()
    proc.kill()


def test_call_injects_the_token(client):
    assert client.call("ping") == "pong"


def test_call_round_trips_arguments(client):
    assert client.call("echo", {"a": [1, 2, 3]}) == {"a": [1, 2, 3]}


def test_a_wrong_token_raises_auth_error(fake_nvda):
    proc = NvdaProcess(
        fake_nvda.argv, fake_nvda.out_dir, token=fake_nvda.token, env=fake_nvda.env, quit_via="rpc"
    )
    handshake = proc.start(timeout=20)
    try:
        rogue = RpcClient.from_handshake(handshake, token="not-the-token")
        with pytest.raises(AuthError, match="stale NVDA"):
            rogue.call("ping")
    finally:
        proc.kill()


def test_an_unknown_method_raises_rpc_error(client):
    with pytest.raises(RpcError, match="no such method"):
        client.call("no_such_method")


def test_a_dead_server_raises_rpc_error_not_oserror(client, fake_nvda):
    client.call("quit")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            client.call("ping")
        except RpcError:
            return
        time.sleep(0.05)
    pytest.fail("calling a dead server should have raised RpcError")


def test_poll_until_returns_the_first_truthy_value(client):
    attempts = []

    def predicate():
        attempts.append(1)
        return "ready" if len(attempts) >= 3 else None

    assert client.poll_until(predicate, timeout=5, description="readiness") == "ready"
    assert len(attempts) == 3


def test_poll_until_reports_what_it_was_waiting_for(client):
    with pytest.raises(WaitTimeout) as excinfo:
        client.poll_until(lambda: None, timeout=0.3, description="speech containing 'hello'")
    assert "speech containing 'hello'" in str(excinfo.value)
    assert excinfo.value.timeout == pytest.approx(0.3, rel=0.5)


def test_poll_until_includes_the_last_value_it_saw(client):
    with pytest.raises(WaitTimeout) as excinfo:
        client.poll_until(
            lambda: None,
            timeout=0.3,
            description="a match",
            last_seen=lambda: ["what", "was", "actually", "said"],
        )
    assert "actually" in str(excinfo.value)


def test_timeout_scale_stretches_polls(fake_nvda):
    proc = NvdaProcess(
        fake_nvda.argv, fake_nvda.out_dir, token=fake_nvda.token, env=fake_nvda.env, quit_via="rpc"
    )
    handshake = proc.start(timeout=20)
    try:
        rpc = RpcClient.from_handshake(handshake, token=fake_nvda.token, timeout_scale=5.0)
        started = time.monotonic()
        with pytest.raises(WaitTimeout):
            rpc.poll_until(lambda: None, timeout=0.2, description="never")
        assert time.monotonic() - started >= 1.0, "0.2s * 5.0 scale should be ~1s"
    finally:
        proc.kill()


def test_protocol_error_is_translated_to_rpc_error(client, monkeypatch):
    def raise_protocol_error(*args, **kwargs):
        raise xmlrpc.client.ProtocolError("127.0.0.1:1/RPC2", 500, "Internal Server Error", {})

    monkeypatch.setattr(client._proxy, "test_method", raise_protocol_error)
    with pytest.raises(RpcError) as excinfo:
        client.call("test_method")
    assert not isinstance(excinfo.value, AuthError)
    assert "500" in str(excinfo.value)


def test_socket_timeout_is_finite_and_applied():
    rpc = RpcClient(1234, "tok", socket_timeout=7.5)
    transport = rpc._proxy._ServerProxy__transport
    assert transport._timeout == 7.5

    rpc_scaled = RpcClient(1234, "tok", socket_timeout=7.5, timeout_scale=2.0)
    transport_scaled = rpc_scaled._proxy._ServerProxy__transport
    assert transport_scaled._timeout == 15.0
