import pytest


@pytest.fixture
def tap():
    from nvda_testkit_spy import log_tap

    log_tap.install()
    log_tap.log_clear()
    yield log_tap
    log_tap.uninstall()


def _emit(level, message):
    from logHandler import log

    getattr(log, level)(message)


def test_records_are_captured_with_their_level(tap):
    _emit("info", "hello from the add-on")
    (record,) = tap.log_since(0)
    assert record["level"] == "INFO"
    assert record["message"] == "hello from the add-on"
    assert record["timestamp"] > 0


def test_index_advances_and_since_slices(tap):
    _emit("info", "one")
    boundary = tap.log_index()
    _emit("error", "two")
    assert [record["message"] for record in tap.log_since(boundary)] == ["two"]


def test_exception_records_carry_their_traceback(tap):
    from logHandler import log

    try:
        raise ValueError("kaboom")
    except ValueError:
        log.exception("something went wrong")
    (record,) = tap.log_since(0)
    assert record["level"] == "ERROR"
    assert "ValueError: kaboom" in record["message"]


def test_clear_resets(tap):
    _emit("info", "noise")
    tap.log_clear()
    assert tap.log_index() == 0


def test_uninstall_detaches_the_handler(tap):
    tap.uninstall()
    _emit("info", "after uninstall")
    tap.install()
    assert tap.log_index() == 0
