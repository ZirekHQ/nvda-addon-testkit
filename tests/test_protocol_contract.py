from __future__ import annotations

import ast
import http.server
import threading
import xmlrpc.client
from pathlib import Path

import pytest

from nvda_testkit.errors import AuthError, ProtocolMismatchError, RpcError, ScenarioSyntaxError
from nvda_testkit.handshake import Handshake
from nvda_testkit.rpcclient import RpcClient, _classify_fault, remote_exception_type
from nvda_testkit.wire import PROTOCOL_VERSION, TOKEN_HEADER

SPY = Path(__file__).parent.parent / "spy" / "globalPlugins" / "nvda_testkit_spy"


def _spy_protocol_versions() -> list[int]:
    found = []
    for source in SPY.glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "PROTOCOL_VERSION" for t in node.targets
                )
                and isinstance(node.value, ast.Constant)
            ):
                found.append(node.value.value)
    return found


def test_spy_declares_the_same_protocol_version_as_the_host():
    assert _spy_protocol_versions() == [PROTOCOL_VERSION]


def _payload(**overrides):
    base = {"port": 1, "pid": 2, "protocolVersion": PROTOCOL_VERSION, "token": "t"}
    return {**base, **overrides}


def test_handshake_carries_token_and_version():
    handshake = Handshake.from_payload(_payload())
    assert (handshake.token, handshake.protocol_version) == ("t", PROTOCOL_VERSION)


@pytest.mark.parametrize("version", [PROTOCOL_VERSION + 1, None])
def test_a_mismatched_or_missing_protocol_version_is_refused(version):
    payload = _payload(protocolVersion=version)
    if version is None:
        del payload["protocolVersion"]
    with pytest.raises(ProtocolMismatchError, match="protocol"):
        Handshake.from_payload(payload)


def test_transport_sends_the_token_header_on_every_request():
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append(self.headers.get(TOKEN_HEADER))
            self.rfile.read(int(self.headers["Content-Length"]))
            body = xmlrpc.client.dumps(("ok",), methodresponse=True).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        rpc = RpcClient(server.server_address[1], "arg-token", header_token="hdr-token")
        assert rpc.call("anything") == "ok"
        assert rpc.call("anything") == "ok"
    finally:
        server.shutdown()
        server.server_close()
    assert seen == ["hdr-token", "hdr-token"]


def test_remote_exception_type_is_parsed_from_the_fault_prefix():
    assert remote_exception_type("<class 'SyntaxError'>:invalid syntax") == "SyntaxError"
    assert remote_exception_type("<class 'builtins.KeyError'>:'x'") == "KeyError"
    assert remote_exception_type("plain text") is None


def test_faults_map_to_typed_errors():
    syntax = xmlrpc.client.Fault(1, "<class 'IndentationError'>:bad")
    auth = xmlrpc.client.Fault(1, "<class 'PermissionError'>:nope")
    other = xmlrpc.client.Fault(1, "<class 'KeyError'>:'x'")
    assert isinstance(_classify_fault("eval_in_nvda", syntax), ScenarioSyntaxError)
    assert type(_classify_fault("speech_index", syntax)) is RpcError
    assert isinstance(_classify_fault("speech_index", auth), AuthError)
    assert type(_classify_fault("speech_index", other)) is RpcError


def test_user_code_mentioning_auth_is_not_an_auth_error():
    wrapped = xmlrpc.client.Fault(1, "<class 'RuntimeError'>:ValueError: AUTH: from a scenario")
    assert type(_classify_fault("eval_in_nvda", wrapped)) is RpcError
