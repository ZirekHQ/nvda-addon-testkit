"""A deliberately boring add-on: it speaks a known phrase on a known gesture,
and writes a known line to the log at startup. That is enough surface for the
kit's own end-to-end tests to assert against.
"""

from typing import ClassVar

import globalPluginHandler
import ui
from core import postNvdaStartup
from logHandler import log

STARTUP_MESSAGE = "testkit demo add-on loaded"
SPOKEN_PHRASE = "testkit demo says hello"


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Sibling add-ons' global plugins load in filesystem-listing order,
        # which NVDA does not guarantee -- logging here directly would race
        # whatever else is watching the log this early. postNvdaStartup fires
        # once every global plugin (including the spy watching this log) has
        # finished loading.
        postNvdaStartup.register(self._logStartup)

    def _logStartup(self):
        log.info(STARTUP_MESSAGE)

    def script_sayHello(self, gesture):
        ui.message(SPOKEN_PHRASE)

    __gestures: ClassVar[dict[str, str]] = {"kb:NVDA+shift+control+d": "sayHello"}
