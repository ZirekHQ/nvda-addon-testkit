import threading
import time

import pytest


def test_runs_the_callable_and_returns_its_value(event_queue):
    from nvda_testkit_spy.mainthread import run_on_main_thread

    assert run_on_main_thread(lambda: "done") == "done"


def test_the_callable_runs_via_the_event_queue_not_inline(event_queue):
    from nvda_testkit_spy.mainthread import run_on_main_thread

    event_queue.auto_drain = False
    calls = []
    result = {}

    def worker():
        result["value"] = run_on_main_thread(lambda: calls.append("ran") or "ok", timeout=5)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=0.3)
    assert calls == []
    event_queue.drain()
    thread.join(timeout=5)
    assert calls == ["ran"]
    assert result["value"] == "ok"


def test_an_exception_is_re_raised_on_the_calling_thread(event_queue):
    from nvda_testkit_spy.mainthread import run_on_main_thread

    def explode():
        raise KeyError("nope")

    with pytest.raises(KeyError, match="nope"):
        run_on_main_thread(explode)


def test_a_never_drained_queue_times_out(event_queue):
    from nvda_testkit_spy.mainthread import run_on_main_thread

    event_queue.auto_drain = False
    with pytest.raises(TimeoutError, match="main thread"):
        run_on_main_thread(lambda: None, timeout=0.2)


def test_a_failure_after_the_caller_timed_out_is_logged(event_queue):
    import logHandler
    from nvda_testkit_spy.mainthread import run_on_main_thread

    logHandler.log.reset_mock()
    event_queue.auto_drain = False

    def explode():
        raise KeyError("too late")

    with pytest.raises(TimeoutError, match="main thread"):
        run_on_main_thread(explode, timeout=0.2)

    event_queue.drain()
    logHandler.log.exception.assert_called_once()


def test_a_never_drained_queue_times_out_saying_it_never_started(event_queue):
    from nvda_testkit_spy.mainthread import run_on_main_thread

    event_queue.auto_drain = False
    with pytest.raises(TimeoutError, match="never started"):
        run_on_main_thread(lambda: None, timeout=0.2)


def test_a_job_that_starts_but_hangs_times_out_saying_it_started(event_queue):
    from nvda_testkit_spy.mainthread import run_on_main_thread

    event_queue.auto_drain = False

    def hang():
        time.sleep(0.4)

    result = {}

    def worker():
        try:
            run_on_main_thread(hang, timeout=0.15)
        except TimeoutError as error:
            result["error"] = error

    thread = threading.Thread(target=worker)
    thread.start()
    while event_queue.empty():
        time.sleep(0.01)
    event_queue.drain()  # runs `hang` right here, on this (the "main") thread
    thread.join(timeout=5)
    assert "did not return" in str(result["error"])
