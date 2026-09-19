"""Where speech begins to count for the next DSL assertion."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionMark:
    index: int = 0
    label: str = ""

    def after(self) -> str:
        return f"after {self.label}" if self.label else "from the start of the test"

    def since(self) -> str:
        return "since that action" if self.label else "since the start of the test"


START = ActionMark()
