# coding: utf-8
"""NVDA Add-on Testkit spy.

Starts a loopback XML-RPC server so nvda-addon-testkit can drive this NVDA.
Does nothing at all unless NVDA_TESTKIT_TOKEN and NVDA_TESTKIT_OUTDIR are both
set, so an accidental install in a real NVDA is inert.
"""

import contextlib
import os

import globalPluginHandler
from logHandler import log

from . import addons_api as addons_api  # re-export: the import alone registers its rpc_method's
from . import braille_tap, log_tap, speech_tap
from . import config_api as config_api  # re-export: the import alone registers its rpc_method's
from . import eval_api as eval_api  # re-export: the import alone registers its rpc_method's
from . import input_api as input_api  # re-export: the import alone registers its rpc_method's
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
            log_tap.install()
            speech_tap.install()
            braille_tap.install()
            self._server = SpyServer(token, out_dir)
            self._server.start()
        except Exception:
            # Log and stay up. A dead spy makes the host time out on the
            # handshake with a clear message; a raising GlobalPlugin
            # constructor takes NVDA's whole add-on load down with it.
            log.exception("nvda-testkit spy failed to start")
            # start() may have already bound a socket and spawned its thread
            # before failing. Dropping the reference without stopping it leaks
            # both for the life of the NVDA process.
            if self._server is not None:
                with contextlib.suppress(Exception):
                    self._server.stop()
            self._server = None
            # install() may have succeeded before SpyServer failed. Left
            # registered, a tap keeps capturing forever with no RPC server
            # alive to ever call its clear().
            with contextlib.suppress(Exception):
                log_tap.uninstall()
            with contextlib.suppress(Exception):
                speech_tap.uninstall()
            with contextlib.suppress(Exception):
                braille_tap.uninstall()

    def terminate(self):
        try:
            log_tap.uninstall()
        except Exception:
            log.exception("nvda-testkit spy failed to remove its log tap")
        try:
            speech_tap.uninstall()
        except Exception:
            log.exception("nvda-testkit spy failed to remove its speech tap")
        try:
            braille_tap.uninstall()
        except Exception:
            log.exception("nvda-testkit spy failed to remove its braille tap")
        if self._server is not None:
            self._server.stop()
            self._server = None
        super().terminate()
