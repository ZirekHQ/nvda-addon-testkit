import json
import subprocess
import sys
import time
import xmlrpc.client
from pathlib import Path

import pytest

FAKE = Path(__file__).parent / "fake_nvda.py"
HANDSHAKE = "testkit-handshake.json"


def _spawn(tmp_path, token="tok", script=None):
    env = {
        "NVDA_TESTKIT_TOKEN": token,
        "NVDA_TESTKIT_OUTDIR": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "SYSTEMROOT": "C:\\Windows",
    }
    if script is not None:
        env["FAKE_NVDA_SCRIPT"] = json.dumps(script)
    return subprocess.Popen([sys.executable, str(FAKE)], env=env)


def _await_handshake(tmp_path, deadline=15.0):
    path = tmp_path / HANDSHAKE
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        if path.is_file():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                pass
        time.sleep(0.02)
    raise AssertionError(f"no handshake file after {deadline}s")


@pytest.fixture
def spawned(tmp_path):
    processes = []

    def spawn(**kwargs):
        proc = _spawn(tmp_path, **kwargs)
        processes.append(proc)
        return proc

    yield spawn
    for proc in processes:
        proc.kill()
        proc.wait(timeout=10)


def test_writes_a_handshake_with_a_reachable_port(spawned, tmp_path):
    spawned()
    handshake = _await_handshake(tmp_path)
    assert handshake["port"] > 0
    assert handshake["pid"] > 0
    assert handshake["nvdaVersion"]
    proxy = xmlrpc.client.ServerProxy(f"http://127.0.0.1:{handshake['port']}", allow_none=True)
    assert proxy.ping("tok") == "pong"


def test_rejects_a_wrong_token(spawned, tmp_path):
    spawned()
    handshake = _await_handshake(tmp_path)
    proxy = xmlrpc.client.ServerProxy(f"http://127.0.0.1:{handshake['port']}", allow_none=True)
    with pytest.raises(xmlrpc.client.Fault) as excinfo:
        proxy.ping("wrong-token")
    # SimpleXMLRPCServer prefixes faultString with the exception type, so the
    # marker is embedded rather than leading. RpcClient matches the same way.
    assert "AUTH:" in excinfo.value.faultString


def test_handshake_delay_knob_is_honoured(spawned, tmp_path):
    started = time.monotonic()
    spawned(script={"handshake_delay": 1.0})
    _await_handshake(tmp_path)
    assert time.monotonic() - started >= 1.0


def test_never_handshake_knob_never_writes_the_file(spawned, tmp_path):
    spawned(script={"never_handshake": True})
    time.sleep(1.0)
    assert not (tmp_path / HANDSHAKE).is_file()


def test_exit_immediately_knob_dies_with_the_given_code(spawned, tmp_path):
    proc = spawned(script={"exit_immediately": 3})
    assert proc.wait(timeout=15) == 3


def test_speech_can_be_emitted_and_read_back(spawned, tmp_path):
    spawned()
    handshake = _await_handshake(tmp_path)
    proxy = xmlrpc.client.ServerProxy(f"http://127.0.0.1:{handshake['port']}", allow_none=True)
    assert proxy.speech_index("tok") == 0
    proxy.speech_emit("tok", [{"kind": "text", "text": "hello world"}])
    assert proxy.speech_index("tok") == 1
    sequences = proxy.speech_since("tok", 0)
    assert sequences[0]["items"][0]["text"] == "hello world"


def test_quit_shuts_the_process_down(spawned, tmp_path):
    proc = spawned()
    handshake = _await_handshake(tmp_path)
    proxy = xmlrpc.client.ServerProxy(f"http://127.0.0.1:{handshake['port']}", allow_none=True)
    proxy.quit("tok")
    assert proc.wait(timeout=15) == 0
