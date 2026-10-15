# coding: utf-8
"""NVDA Add-on Testkit spy.

Starts a loopback XML-RPC server so nvda-addon-testkit can drive this NVDA.
Does nothing at all unless NVDA_TESTKIT_TOKEN and NVDA_TESTKIT_OUTDIR are both
set, so an accidental install in a real NVDA is inert.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import globalPluginHandler
from logHandler import log

from . import addons_api as addons_api
from . import braille_tap, log_tap, speech_tap
from . import config_api as config_api
from . import eval_api as eval_api
from . import input_api as input_api
from . import modal_api as modal_api
from .server import SpyServer
from .settings import Settings


def _best_effort(action: Callable[[], None], failure: str) -> None:
    """Run one teardown step so a failure never skips the steps after it."""
    try:
        action()
    except Exception:
        log.exception(failure)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._server: Optional[SpyServer] = None

        settings = Settings.from_environ()
        if settings is None:
            log.info("nvda-testkit spy present but idle: no session environment set")
            return

        try:
            log_tap.install()
            speech_tap.install()
            braille_tap.install()
            self._server = SpyServer(settings.token, settings.out_dir)
            self._server.start()
        except Exception:
            log.exception("nvda-testkit spy failed to start")
            self._teardown()

    def _teardown(self) -> None:
        if self._server is not None:
            _best_effort(self._server.stop, "nvda-testkit spy failed to stop its server")
        self._server = None
        _best_effort(log_tap.uninstall, "nvda-testkit spy failed to remove its log tap")
        _best_effort(speech_tap.uninstall, "nvda-testkit spy failed to remove its speech tap")
        _best_effort(braille_tap.uninstall, "nvda-testkit spy failed to remove its braille tap")

    def terminate(self) -> None:
        self._teardown()
        super().terminate()
