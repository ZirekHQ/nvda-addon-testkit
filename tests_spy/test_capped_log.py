import pytest
from nvda_testkit_spy.capped_log import CappedLog


@pytest.fixture
def log():
    return CappedLog(capacity=3)


def test_an_empty_log_starts_at_index_zero(log):
    assert log.index() == 0
    assert log.since(0) == []


def test_since_returns_entries_after_the_index(log):
    log.append({"n": 1})
    boundary = log.index()
    log.append({"n": 2})
    assert log.since(boundary) == [{"n": 2}]


def test_the_oldest_entries_are_dropped_beyond_capacity(log):
    for n in range(5):
        log.append({"n": n})
    assert [entry["n"] for entry in log.since(0)] == [2, 3, 4]


def test_indices_keep_counting_past_evictions(log):
    for n in range(5):
        log.append({"n": n})
    assert log.index() == 5
    assert [entry["n"] for entry in log.since(4)] == [4]


def test_since_returns_copies(log):
    log.append({"n": 1})
    log.since(0)[0]["n"] = 99
    assert log.since(0) == [{"n": 1}]


def test_mark_last_updates_the_newest_entry(log):
    log.append({"n": 1})
    log.append({"n": 2})
    assert log.mark_last(cancelled=True) is True
    assert log.since(0) == [{"n": 1}, {"n": 2, "cancelled": True}]


def test_mark_last_on_an_empty_log_reports_nothing_marked(log):
    assert log.mark_last(cancelled=True) is False


def test_clear_resets_entries_and_index(log):
    for n in range(5):
        log.append({"n": n})
    log.clear()
    assert log.index() == 0
    assert log.since(0) == []
