import pytest

from nvda_testkit import __version__
from nvda_testkit.errors import (
    AuthError,
    HandshakeTimeout,
    HashMismatchError,
    LauncherResolutionError,
    NvdaStartupError,
    ProvisionError,
    RpcError,
    TestkitError,
    UnsupportedPlatformError,
    WaitTimeout,
)


def test_version_is_a_dotted_string():
    assert __version__.count(".") >= 2


@pytest.mark.parametrize(
    ("child", "parent"),
    [
        (ProvisionError, TestkitError),
        (LauncherResolutionError, ProvisionError),
        (HashMismatchError, ProvisionError),
        (UnsupportedPlatformError, TestkitError),
        (NvdaStartupError, TestkitError),
        (HandshakeTimeout, NvdaStartupError),
        (RpcError, TestkitError),
        (AuthError, RpcError),
        (WaitTimeout, TestkitError),
    ],
)
def test_hierarchy(child, parent):
    assert issubclass(child, parent)


def test_hash_mismatch_reports_both_digests():
    err = HashMismatchError(expected="aaa", actual="bbb", path="/tmp/x.exe")
    assert "aaa" in str(err)
    assert "bbb" in str(err)
    assert "/tmp/x.exe" in str(err)
