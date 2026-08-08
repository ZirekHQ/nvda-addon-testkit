"""A deliberately boring add-on: it speaks a known phrase on a known gesture,
and writes a known line to the log at startup. That is enough surface for the
kit's own end-to-end tests to assert against.
"""

from typing import ClassVar

import globalPluginHandler
import ui
from logHandler import log

STARTUP_MESSAGE = "testkit demo add-on loaded"
SPOKEN_PHRASE = "testkit demo says hello"


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        log.info(STARTUP_MESSAGE)

    def script_sayHello(self, gesture):
        ui.message(SPOKEN_PHRASE)

    __gestures: ClassVar[dict[str, str]] = {"kb:NVDA+shift+control+d": "sayHello"}
