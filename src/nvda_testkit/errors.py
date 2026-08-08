"""Exception hierarchy. Every error the kit raises descends from TestkitError."""


class TestkitError(Exception):
    """Base for every error raised by nvda-addon-testkit."""


class ProvisionError(TestkitError):
    """Failed to obtain or prepare an NVDA to test against."""


class LauncherResolutionError(ProvisionError):
    """Could not work out which NVDA launcher to download."""


class HashMismatchError(ProvisionError):
    """A downloaded launcher did not match its published digest."""

    def __init__(self, *, expected: str, actual: str, path: str) -> None:
        self.expected = expected
        self.actual = actual
        self.path = path
        super().__init__(
            f"Launcher digest mismatch for {path}: expected {expected}, got {actual}. "
            "Refusing to execute it."
        )


class UnsupportedPlatformError(TestkitError):
    """This operation needs a real Windows host."""


class NvdaStartupError(TestkitError):
    """NVDA failed to start, or died before it was usable."""


class HandshakeTimeout(NvdaStartupError):
    """NVDA started but the spy add-on never announced itself."""


class RpcError(TestkitError):
    """A call into the spy add-on failed."""


class AuthError(RpcError):
    """The spy rejected our token. Almost always a stale NVDA from a previous run."""


class WaitTimeout(TestkitError):
    """A deadline-bounded poll expired before its predicate came true."""

    def __init__(self, description: str, timeout: float, last_seen: object = None) -> None:
        self.description = description
        self.timeout = timeout
        self.last_seen = last_seen
        message = f"Timed out after {timeout:.1f}s waiting for {description}."
        if last_seen is not None:
            message += f" Last seen: {last_seen!r}"
        super().__init__(message)
