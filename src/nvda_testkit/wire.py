"""The host-side schema for everything that crosses the RPC boundary.

Handshake file (`testkit-handshake.json`, written by the spy once listening):

    {"port": int, "pid": int, "protocolVersion": int, "token": str,
     "nvdaVersion": str, "apiVersion": str | null, "apiCompatTo": str | null}

Every XML-RPC call carries the session token twice: as the first positional
argument, and as the `X-Testkit-Token` HTTP header, which the spy checks
before dispatch and answers with HTTP 401 when absent or wrong.

The spy's own `PROTOCOL_VERSION` must equal `PROTOCOL_VERSION` here; a
contract test parses the spy source to enforce it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeAlias

PROTOCOL_VERSION = 1
TOKEN_HEADER = "X-Testkit-Token"

WirePayload: TypeAlias = Mapping[str, Any]
ConfigSnapshot: TypeAlias = dict[str, Any]
ConfigPath: TypeAlias = str | Sequence[str]
