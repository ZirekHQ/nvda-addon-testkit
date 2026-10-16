import http.client
import json
import os
import socket
import stat
import sys
import threading
import xmlrpc.client

import core
import logHandler
import pytest
from nvda_testkit_spy import server as server_module
from nvda_testkit_spy.server import (
    HANDSHAKE_FILENAME,
    PROTOCOL_VERSION,
    TOKEN_HEADER,
    SpyServer,
)

from nvda_testkit.process import HANDSHAKE_FILENAME as HOST_NAME


@pytest.fixture
def running(tmp_path, event_queue):
    """A started SpyServer and its port; stopped afterwards."""
    server = SpyServer("tok", tmp_path)
    port = server.start()
    yield server, port
    server.stop()


@pytest.fixture
def session_token(running, tmp_path):
    return json.loads((tmp_path / HANDSHAKE_FILENAME).read_text())["token"]


@pytest.fixture
def proxy(running, session_token):
    _, port = running
    return xmlrpc.client.ServerProxy(
        f"http://127.0.0.1:{port}",
        allow_none=True,
        headers=[(TOKEN_HEADER, session_token)],
    )


def _post_status(port, headers, body=None):
    body = xmlrpc.client.dumps(("tok",), "ping") if body is None else body
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("POST", "/RPC2", body, headers)
        return connection.getresponse().status
    finally:
        connection.close()


def test_a_post_without_the_token_header_is_401(running):
    _, port = running
    assert _post_status(port, {}) == 401


def test_a_rejected_post_with_a_large_body_still_reads_the_401(running):
    _, port = running
    body = "x" * (4 * 1024 * 1024)
    assert _post_status(port, {}, body) == 401


def test_a_rejected_post_that_stalls_mid_body_still_gets_the_401(running, monkeypatch):
    _, port = running
    monkeypatch.setattr(server_module, "DISCARD_DEADLINE", 0.3)
    with socket.create_connection(("127.0.0.1", port), timeout=5) as stalled:
        stalled.sendall(
            b"POST /RPC2 HTTP/1.1\r\nHost: x\r\nContent-Length: 1000000\r\n\r\nonly a few bytes"
        )
        assert stalled.recv(64).startswith(b"HTTP/1.0 401")


def test_a_post_with_the_wrong_token_header_is_401(running):
    _, port = running
    assert _post_status(port, {TOKEN_HEADER: "wrong"}) == 401


def test_a_post_with_the_right_token_header_is_served(running, session_token):
    _, port = running
    assert _post_status(port, {TOKEN_HEADER: session_token}) == 200


def test_the_handshake_carries_the_token_and_protocol_version(running, tmp_path, session_token):
    payload = json.loads((tmp_path / HANDSHAKE_FILENAME).read_text())
    assert len(session_token) >= 32
    assert payload["protocolVersion"] == PROTOCOL_VERSION == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_the_handshake_file_is_owner_only(running, tmp_path):
    mode = stat.S_IMODE(os.stat(tmp_path / HANDSHAKE_FILENAME).st_mode)
    assert mode == 0o600


def test_start_binds_a_port_and_writes_a_handshake(running, tmp_path):
    _, port = running
    payload = json.loads((tmp_path / HANDSHAKE_FILENAME).read_text())
    assert port > 0
    assert payload["port"] == port
    assert payload["nvdaVersion"] == "2026.1.1"
    assert payload["apiCompatTo"] == "2026.1.0"


def test_the_handshake_filename_matches_the_host_side():
    assert HOST_NAME == HANDSHAKE_FILENAME


def test_core_methods_answer_over_the_wire(proxy):
    assert proxy.ping("tok") == "pong"
    assert proxy.echo("tok", [1, 2]) == [1, 2]
    assert proxy.nvda_version("tok")["version"] == "2026.1.1"
    assert proxy.wait_until_idle("tok", 5.0) is True


def test_the_handshake_is_never_visible_half_written(running, tmp_path):
    assert not (tmp_path / (HANDSHAKE_FILENAME + ".part")).exists()
    json.loads((tmp_path / HANDSHAKE_FILENAME).read_text())


def test_a_wrong_token_faults_over_the_wire_with_the_auth_prefix(proxy):
    with pytest.raises(xmlrpc.client.Fault, match="AUTH:"):
        proxy.ping("wrong")


def test_an_unknown_method_faults_over_the_wire_with_the_unknown_prefix(proxy):
    with pytest.raises(xmlrpc.client.Fault, match="UNKNOWN:"):
        proxy.nope("tok")


def test_quit_asks_nvda_to_exit_from_the_main_thread(proxy, event_queue):
    core.triggerNVDAExit.reset_mock()
    event_queue.auto_drain = False
    result = {}
    caller = threading.Thread(target=lambda: result.update(value=proxy.quit("tok")))
    caller.start()
    caller.join(timeout=0.3)
    assert core.triggerNVDAExit.call_count == 0, "quit must wait for the main thread"
    event_queue.drain()
    caller.join(timeout=5)
    assert result["value"] is True
    assert core.triggerNVDAExit.call_count == 1


def test_stop_removes_the_handshake(tmp_path, event_queue):
    server = SpyServer("tok", tmp_path)
    server.start()
    (tmp_path / (HANDSHAKE_FILENAME + ".part")).write_text("{}")
    server.stop()
    assert not (tmp_path / HANDSHAKE_FILENAME).exists()
    assert not (tmp_path / (HANDSHAKE_FILENAME + ".part")).exists()


def test_stop_is_idempotent(tmp_path, event_queue):
    server = SpyServer("tok", tmp_path)
    server.start()
    server.stop()
    server.stop()


class _StuckServer:
    """A server whose serve loop never lets shutdown() return."""

    def __init__(self):
        self.release = threading.Event()
        self.closed = False

    def shutdown(self):
        self.release.wait(timeout=10)

    def server_close(self):
        self.closed = True


def test_stop_does_not_block_when_the_serve_loop_is_stuck_in_a_handler(tmp_path):
    stuck = _StuckServer()
    server = SpyServer("tok", tmp_path, stop_timeout=0.2)
    server._server = stuck

    finished = threading.Event()
    stopper = threading.Thread(target=lambda: (server.stop(), finished.set()))
    stopper.start()
    try:
        assert finished.wait(timeout=3), "stop() must return after its timeout, not hang"
        assert stuck.closed
        assert server._server is None
    finally:
        stuck.release.set()
        stopper.join(timeout=5)


def test_stop_logs_when_the_serve_loop_did_not_stop(tmp_path):
    logHandler.log.reset_mock()
    stuck = _StuckServer()
    server = SpyServer("tok", tmp_path, stop_timeout=0.05)
    server._server = stuck
    try:
        server.stop()
    finally:
        stuck.release.set()
    logHandler.log.warning.assert_called_once()


def test_the_default_stop_timeout_is_bounded():
    assert 0 < server_module.STOP_TIMEOUT <= 30
