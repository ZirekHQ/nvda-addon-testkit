"""The e2e error allowlist never runs on Linux, so its logic is pinned down here.

Loaded under an explicit module name: `conftest` is already taken by this suite's own.
"""

import importlib.util
from pathlib import Path

import pytest

from nvda_testkit.namespaces.log import LogRecord

E2E_CONFTEST = Path(__file__).resolve().parents[1] / "tests_e2e" / "conftest.py"


def _load():
    spec = importlib.util.spec_from_file_location("nvda_testkit_e2e_conftest", E2E_CONFTEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeLog:
    def __init__(self, records):
        self._records = records

    def errors(self, *, since=0):
        return self._records[since:]


class _FakeClient:
    def __init__(self, records):
        self.log = _FakeLog(records)


@pytest.fixture(scope="module")
def e2e():
    return _load()


def test_an_addon_error_is_never_allowlisted(e2e):
    client = _FakeClient([LogRecord("ERROR", "testkit-demo: onInstall raised")])
    with pytest.raises(AssertionError, match="1 unexpected error"):
        e2e.check_no_unexpected_errors(client)


def test_a_clean_log_passes_without_warning(e2e, recwarn):
    e2e.check_no_unexpected_errors(_FakeClient([]))
    assert len(recwarn) == 0


@pytest.mark.parametrize(
    "message",
    [
        "Error in nvwave: could not open the audio device",
        "Error initializing synthDriver espeak",
        "Could not load braille display driver noBraille",
        "UIAHandler: error registering for events",
    ],
)
def test_known_runner_noise_is_allowlisted(e2e, message):
    client = _FakeClient([LogRecord("ERROR", message)])
    with pytest.warns(UserWarning, match="runner-environment error"):
        e2e.check_no_unexpected_errors(client)


def test_allowlisted_records_are_still_quoted_when_something_else_fails(e2e):
    client = _FakeClient(
        [
            LogRecord("ERROR", "Error in nvwave: no audio device"),
            LogRecord("ERROR", "testkit-demo blew up"),
        ]
    )
    with pytest.warns(UserWarning), pytest.raises(AssertionError) as failure:
        e2e.check_no_unexpected_errors(client)
    assert "testkit-demo blew up" in str(failure.value)
    assert "nvwave" in str(failure.value), "the allowlisted ones must stay visible"


def test_since_is_honoured(e2e):
    client = _FakeClient([LogRecord("ERROR", "before"), LogRecord("ERROR", "after")])
    with pytest.raises(AssertionError) as failure:
        e2e.check_no_unexpected_errors(client, since=1)
    assert "before" not in str(failure.value)
