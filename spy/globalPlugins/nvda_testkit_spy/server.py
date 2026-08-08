# coding: utf-8
"""The loopback XML-RPC server, and the handful of core methods.

Binds 127.0.0.1 only, on an ephemeral port, and publishes that port through a
handshake file written with write-then-rename so the host never reads a
half-written one.
"""

import json
import os
import threading
from xmlrpc.server import SimpleXMLRPCServer

import queueHandler
from logHandler import log

from .mainthread import run_on_main_thread
from .registry import Dispatcher, rpc_method

#: Wire contract with nvda_testkit.process.HANDSHAKE_FILENAME. Keep in step.
HANDSHAKE_FILENAME = "testkit-handshake.json"


def _nvda_versions():
    import addonAPIVersion
    import versionInfo

    return {
        "version": versionInfo.version,
        "apiVersion": addonAPIVersion.formatForGUI(addonAPIVersion.CURRENT),
        "apiCompatTo": addonAPIVersion.formatForGUI(addonAPIVersion.BACK_COMPAT_TO),
    }


@rpc_method
def ping():
    return "pong"


@rpc_method
def echo(value):
    return value


@rpc_method
def nvda_version():
    return _nvda_versions()


@rpc_method
def wait_until_idle(timeout=10.0):
    """Return once NVDA's event queue has drained past this point.

    Queueing a no-op and waiting for it to run proves the queue reached here;
    checking the queue is then empty proves nothing new arrived behind it.
    """
    run_on_main_thread(lambda: None, timeout=timeout)
    return queueHandler.eventQueue.empty()


@rpc_method
def quit():
    import core

    core.triggerNVDAExit()
    return True


class SpyServer:
    def __init__(self, token, out_dir):
        self._token = token
        self._out_dir = out_dir
        self._server = None
        self._thread = None

    def start(self):
        self._server = SimpleXMLRPCServer(("127.0.0.1", 0), allow_none=True, logRequests=False)
        self._server.register_instance(Dispatcher(self._token), allow_dotted_names=False)
        port = self._server.server_address[1]

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="nvda_testkit_spy",
            daemon=True,
        )
        self._thread.start()
        self._write_handshake(port)
        log.info("nvda-testkit spy listening on 127.0.0.1:%d" % port)
        return port

    def _write_handshake(self, port):
        payload = _nvda_versions()
        payload = {
            "port": port,
            "pid": os.getpid(),
            "nvdaVersion": payload["version"],
            "apiVersion": payload["apiVersion"],
            "apiCompatTo": payload["apiCompatTo"],
        }
        if not os.path.isdir(self._out_dir):
            os.makedirs(self._out_dir)
        final = os.path.join(self._out_dir, HANDSHAKE_FILENAME)
        temporary = final + ".part"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(temporary, final)

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self._thread = None
