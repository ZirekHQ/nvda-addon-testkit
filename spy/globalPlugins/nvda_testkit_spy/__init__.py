# coding: utf-8
"""NVDA Add-on Testkit spy.

Starts a loopback XML-RPC server so nvda-addon-testkit can drive this NVDA.
Does nothing at all unless NVDA_TESTKIT_TOKEN and NVDA_TESTKIT_OUTDIR are both
set, so an accidental install in a real NVDA is inert.
"""

import os

import globalPluginHandler
from logHandler import log

from .server import SpyServer


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._server = None

        token = os.environ.get("NVDA_TESTKIT_TOKEN")
        out_dir = os.environ.get("NVDA_TESTKIT_OUTDIR")
        if not token or not out_dir:
            log.info("nvda-testkit spy present but idle: no session environment set")
            return

        try:
            self._server = SpyServer(token, out_dir)
            self._server.start()
        except Exception:
            # Log and stay up. A dead spy makes the host time out on the
            # handshake with a clear message; a raising GlobalPlugin
            # constructor takes NVDA's whole add-on load down with it.
            log.exception("nvda-testkit spy failed to start")
            self._server = None

    def terminate(self):
        if self._server is not None:
            self._server.stop()
            self._server = None
        super().terminate()
