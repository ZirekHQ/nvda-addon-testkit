import json
import xmlrpc.client


def test_start_binds_a_port_and_writes_a_handshake(tmp_path, event_queue):
    from nvda_testkit_spy.server import HANDSHAKE_FILENAME, SpyServer

    server = SpyServer("tok", tmp_path)
    port = server.start()
    try:
        assert port > 0
        payload = json.loads((tmp_path / HANDSHAKE_FILENAME).read_text())
        assert payload["port"] == port
        assert payload["nvdaVersion"] == "2026.1.1"
        assert payload["apiCompatTo"] == "2026.1.0"
    finally:
        server.stop()


def test_the_handshake_filename_matches_the_host_side(tmp_path):
    from nvda_testkit_spy.server import HANDSHAKE_FILENAME as SPY_NAME

    from nvda_testkit.process import HANDSHAKE_FILENAME as HOST_NAME

    assert HOST_NAME == SPY_NAME


def test_core_methods_answer_over_the_wire(tmp_path, event_queue):
    from nvda_testkit_spy.server import SpyServer

    server = SpyServer("tok", tmp_path)
    port = server.start()
    try:
        proxy = xmlrpc.client.ServerProxy(f"http://127.0.0.1:{port}", allow_none=True)
        assert proxy.ping("tok") == "pong"
        assert proxy.echo("tok", [1, 2]) == [1, 2]
        version = proxy.nvda_version("tok")
        assert version["version"] == "2026.1.1"
        assert proxy.wait_until_idle("tok", 5.0) is True
    finally:
        server.stop()


def test_the_handshake_is_never_visible_half_written(tmp_path, event_queue):
    from nvda_testkit_spy.server import HANDSHAKE_FILENAME, SpyServer

    server = SpyServer("tok", tmp_path)
    server.start()
    try:
        # A .part file must not survive; the rename is the publication step.
        assert not (tmp_path / (HANDSHAKE_FILENAME + ".part")).exists()
        json.loads((tmp_path / HANDSHAKE_FILENAME).read_text())
    finally:
        server.stop()
