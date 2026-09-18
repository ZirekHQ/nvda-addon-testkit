import pytest


@pytest.fixture
def api():
    from nvda_testkit_spy import modal_api

    return modal_api


def _fake_kernel32(pid):
    return type("FakeKernel32", (), {"GetCurrentProcessId": staticmethod(lambda: pid)})


def test_it_is_registered_under_the_name_the_host_calls():
    from nvda_testkit_spy import modal_api  # noqa: F401  -- importing is what registers it
    from nvda_testkit_spy.registry import METHODS

    assert "simulate_modal" in METHODS


def test_an_unknown_gesture_raises_before_any_polling(api, monkeypatch):
    polled = []
    monkeypatch.setattr(api, "_foreground_owner", lambda: polled.append(1) or (None, None))
    with pytest.raises(ValueError, match="doesn't know gesture"):
        api.simulate_modal("triple-click")
    assert polled == []


def test_it_sends_the_gesture_once_our_process_takes_the_foreground(api, monkeypatch):
    monkeypatch.setattr(api, "_kernel32", lambda: _fake_kernel32(42))
    owners = iter([(100, 7), (100, 7), (200, 42)])
    monkeypatch.setattr(api, "_foreground_owner", lambda: next(owners))
    sent = []
    monkeypatch.setattr(api, "_send_vk", lambda vk: sent.append(vk))

    assert api.simulate_modal("enter", timeout=1, poll_interval=0) is True
    assert sent == [api._VK["enter"]]


def test_it_gives_up_and_returns_false_if_nothing_takes_the_foreground(api, monkeypatch):
    monkeypatch.setattr(api, "_kernel32", lambda: _fake_kernel32(42))
    monkeypatch.setattr(api, "_foreground_owner", lambda: (100, 7))
    sent = []
    monkeypatch.setattr(api, "_send_vk", lambda vk: sent.append(vk))

    assert api.simulate_modal("enter", timeout=0.05, poll_interval=0.01) is False
    assert sent == []


def test_it_ignores_a_foreground_window_owned_by_another_process(api, monkeypatch):
    monkeypatch.setattr(api, "_kernel32", lambda: _fake_kernel32(42))
    monkeypatch.setattr(api, "_foreground_owner", lambda: (999, 12345))
    sent = []
    monkeypatch.setattr(api, "_send_vk", lambda vk: sent.append(vk))

    assert api.simulate_modal("enter", timeout=0.05, poll_interval=0.01) is False
    assert sent == []
