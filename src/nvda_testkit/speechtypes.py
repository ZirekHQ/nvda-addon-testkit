"""Host-side representation of a captured speech sequence.

Deliberately not NVDA's own SpeechSequence: these come off the wire as plain
dicts, and the point is that a test can assert on them without importing
anything from NVDA.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SpeechItem:
    kind: str
    text: str | None = None
    command_type: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)
    raw: str | None = None

    @classmethod
    def from_payload(cls, payload: dict) -> SpeechItem:
        if payload.get("kind") == "text":
            return cls(kind="text", text=payload.get("text", ""))
        return cls(
            kind="command",
            command_type=payload.get("type"),
            fields=dict(payload.get("fields") or {}),
            raw=payload.get("repr"),
        )

    def __repr__(self) -> str:
        if self.kind == "text":
            return f"text({self.text!r})"
        return f"{self.command_type}({self.fields})"


@dataclass(frozen=True)
class SpeechSequence:
    items: tuple[SpeechItem, ...]
    timestamp: float = 0.0
    cancelled: bool = False

    @property
    def text(self) -> str:
        joined = " ".join(item.text for item in self.items if item.kind == "text" and item.text)
        return re.sub(r"\s+", " ", joined).strip()

    def commands(self, type_name: str) -> list[SpeechItem]:
        return [item for item in self.items if item.command_type == type_name]

    def matches(self, pattern: str, *, flags: int = re.IGNORECASE) -> bool:
        return re.search(pattern, self.text, flags) is not None

    def __repr__(self) -> str:
        suffix = " [cancelled]" if self.cancelled else ""
        return f"<SpeechSequence {self.text!r}{suffix}>"


def parse_sequence(payload: dict) -> SpeechSequence:
    return SpeechSequence(
        items=tuple(SpeechItem.from_payload(item) for item in payload.get("items") or []),
        timestamp=float(payload.get("timestamp") or 0.0),
        cancelled=bool(payload.get("cancelled")),
    )


def parse_sequences(payloads: list[dict]) -> list[SpeechSequence]:
    return [parse_sequence(payload) for payload in payloads]
