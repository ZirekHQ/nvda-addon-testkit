"""The handshake the spy writes once its RPC server is listening."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import ProtocolMismatchError
from .wire import PROTOCOL_VERSION, WirePayload


@dataclass(frozen=True)
class Handshake:
    port: int
    pid: int
    nvda_version: str
    api_version: str | None
    api_compat_to: str | None
    protocol_version: int = PROTOCOL_VERSION
    token: str | None = None

    @classmethod
    def from_payload(cls, payload: WirePayload) -> Handshake:
        port = int(payload["port"])
        pid = int(payload["pid"])
        advertised = payload.get("protocolVersion")
        if advertised != PROTOCOL_VERSION:
            raise ProtocolMismatchError(
                f"The spy speaks protocol {advertised!r}; this nvda-addon-testkit speaks "
                f"{PROTOCOL_VERSION}. Rebuild the spy bundle (python tools/build_spy.py) "
                "or align the installed nvda-addon-testkit version."
            )
        token = payload.get("token")
        return cls(
            port=port,
            pid=pid,
            nvda_version=str(payload.get("nvdaVersion", "unknown")),
            api_version=payload.get("apiVersion"),
            api_compat_to=payload.get("apiCompatTo"),
            protocol_version=int(advertised),
            token=str(token) if token else None,
        )
