import pytest


@pytest.fixture
def api():
    from nvda_testkit_spy import modal_api

    modal_api._pending_baseline["hwnd"] = modal_api._UNSET
    return modal_api


def _fake_kernel32(pid):
    return type("FakeKernel32", (), {"GetCurrentProcessId": staticmethod(lambda: pid)})


def _fake_user32(**methods):
    return type("FakeUser32", (), {name: staticmethod(fn) for name, fn in methods.items()})


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


@pytest.mark.parametrize("gesture", [["enter"], {"k": "enter"}, 13, None])
def test_a_non_string_gesture_raises_value_error(api, gesture):
    with pytest.raises(ValueError, match="doesn't know gesture"):
        api.simulate_modal(gesture)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout": "5"},
        {"timeout": [1]},
        {"timeout": float("inf")},
        {"timeout": float("nan")},
        {"timeout": -1},
        {"poll_interval": "x"},
        {"poll_interval": float("inf")},
        {"poll_interval": -0.1},
    ],
)
def test_invalid_timing_raises_value_error_before_any_polling(api, monkeypatch, kwargs):
    polled = []
    monkeypatch.setattr(api, "_foreground_owner", lambda: polled.append(1) or (None, None))
    with pytest.raises(ValueError, match="simulate_modal"):
        api.simulate_modal("enter", **kwargs)
    assert polled == []


def test_a_zero_timeout_returns_false_immediately(api, monkeypatch):
    monkeypatch.setattr(api, "_kernel32", lambda: _fake_kernel32(42))
    monkeypatch.setattr(api, "_foreground_owner", lambda: (100, 7))
    assert api.simulate_modal("enter", timeout=0) is False


def test_a_dialog_foregrounded_before_the_call_counts_against_the_recorded_baseline(
    api, monkeypatch
):
    """exec_nowait queues a ShowModal() scenario that can foreground its
    dialog before simulate_modal's own RPC even arrives. The baseline taken
    at queue time, not at poll start, is what keeps that dialog from being
    mistaken for the window that was already there."""
    monkeypatch.setattr(api, "_kernel32", lambda: _fake_kernel32(42))
    monkeypatch.setattr(api, "_foreground_owner", lambda: (200, 42))
    monkeypatch.setattr(api, "_is_owned_modal", lambda hwnd: True)
    sent = []
    monkeypatch.setattr(api, "_send_vk", lambda vk: sent.append(vk))
    api._pending_baseline["hwnd"] = 100

    assert api.simulate_modal("enter", timeout=1, poll_interval=0) is True
    assert sent == [api._VK["enter"]]


def test_the_recorded_baseline_is_consumed_by_one_call(api, monkeypatch):
    monkeypatch.setattr(api, "_kernel32", lambda: _fake_kernel32(42))
    monkeypatch.setattr(api, "_foreground_owner", lambda: (200, 42))
    monkeypatch.setattr(api, "_is_owned_modal", lambda hwnd: True)
    monkeypatch.setattr(api, "_send_vk", lambda vk: None)
    api._pending_baseline["hwnd"] = 100
    api.simulate_modal("enter", timeout=1, poll_interval=0)

    assert api.simulate_modal("enter", timeout=0.05, poll_interval=0.01) is False


def test_remember_foreground_baseline_stores_the_current_foreground_hwnd(api, monkeypatch):
    monkeypatch.setattr(api, "_foreground_owner", lambda: (321, 42))
    api.remember_foreground_baseline()
    assert api._pending_baseline["hwnd"] == 321


def test_it_sends_the_gesture_once_our_process_owns_a_modal_in_the_foreground(api, monkeypatch):
    monkeypatch.setattr(api, "_kernel32", lambda: _fake_kernel32(42))
    owners = iter([(100, 7), (100, 7), (200, 42)])
    monkeypatch.setattr(api, "_foreground_owner", lambda: next(owners))
    monkeypatch.setattr(api, "_is_owned_modal", lambda hwnd: True)
    sent = []
    monkeypatch.setattr(api, "_send_vk", lambda vk: sent.append(vk))

    assert api.simulate_modal("enter", timeout=1, poll_interval=0) is True
    assert sent == [api._VK["enter"]]


def test_it_rejects_a_window_that_was_already_foreground_at_poll_start(api, monkeypatch):
    """Confirmed against a real NVDA: an already-foreground, ownerless
    window (NVDA's own main frame, say) is indistinguishable from an
    ownerless dialog by _is_owned_modal alone. Requiring the foreground
    hwnd to change is what keeps that window from eating the gesture
    before the real dialog has even opened."""
    monkeypatch.setattr(api, "_kernel32", lambda: _fake_kernel32(42))
    monkeypatch.setattr(api, "_foreground_owner", lambda: (100, 42))
    monkeypatch.setattr(api, "_is_owned_modal", lambda hwnd: True)
    sent = []
    monkeypatch.setattr(api, "_send_vk", lambda vk: sent.append(vk))

    assert api.simulate_modal("enter", timeout=0.05, poll_interval=0.01) is False
    assert sent == []


def test_it_rejects_a_changed_owned_window_that_is_not_modal(api, monkeypatch):
    """A same-process window newly taking the foreground that isn't the
    modal dialog (e.g. some other popup) must not eat the keystroke meant
    for a modal that hasn't opened yet."""
    monkeypatch.setattr(api, "_kernel32", lambda: _fake_kernel32(42))
    owners = iter([(100, 7), (200, 42)])
    monkeypatch.setattr(api, "_foreground_owner", lambda: next(owners, (200, 42)))
    monkeypatch.setattr(api, "_is_owned_modal", lambda hwnd: False)
    sent = []
    monkeypatch.setattr(api, "_send_vk", lambda vk: sent.append(vk))

    assert api.simulate_modal("enter", timeout=0.05, poll_interval=0.01) is False
    assert sent == []


def test_it_gives_up_and_returns_false_if_nothing_takes_the_foreground(api, monkeypatch):
    monkeypatch.setattr(api, "_kernel32", lambda: _fake_kernel32(42))
    monkeypatch.setattr(api, "_foreground_owner", lambda: (100, 7))
    monkeypatch.setattr(api, "_is_owned_modal", lambda hwnd: True)
    sent = []
    monkeypatch.setattr(api, "_send_vk", lambda vk: sent.append(vk))

    assert api.simulate_modal("enter", timeout=0.05, poll_interval=0.01) is False
    assert sent == []


def test_it_ignores_a_foreground_window_owned_by_another_process(api, monkeypatch):
    monkeypatch.setattr(api, "_kernel32", lambda: _fake_kernel32(42))
    monkeypatch.setattr(api, "_foreground_owner", lambda: (999, 12345))
    monkeypatch.setattr(api, "_is_owned_modal", lambda hwnd: True)
    sent = []
    monkeypatch.setattr(api, "_send_vk", lambda vk: sent.append(vk))

    assert api.simulate_modal("enter", timeout=0.05, poll_interval=0.01) is False
    assert sent == []


def test_is_owned_modal_true_when_the_owner_window_is_disabled(api, monkeypatch):
    monkeypatch.setattr(
        api,
        "_user32",
        lambda: _fake_user32(GetWindow=lambda hwnd, flag: 55, IsWindowEnabled=lambda hwnd: False),
    )
    assert api._is_owned_modal(100) is True


def test_is_owned_modal_false_when_the_owner_window_is_still_enabled(api, monkeypatch):
    monkeypatch.setattr(
        api,
        "_user32",
        lambda: _fake_user32(GetWindow=lambda hwnd, flag: 55, IsWindowEnabled=lambda hwnd: True),
    )
    assert api._is_owned_modal(100) is False


def test_is_owned_modal_falls_back_to_true_with_no_owner_window(api, monkeypatch):
    monkeypatch.setattr(api, "_user32", lambda: _fake_user32(GetWindow=lambda hwnd, flag: 0))
    assert api._is_owned_modal(100) is True


def test_send_vk_succeeds_when_both_events_are_inserted(api, monkeypatch):
    calls = []
    monkeypatch.setattr(
        api, "_user32", lambda: _fake_user32(SendInput=lambda *a: calls.append(a) or 1)
    )
    api._send_vk(api._VK["enter"])
    assert len(calls) == 2


def test_send_vk_raises_when_sendinput_is_rejected(api, monkeypatch):
    monkeypatch.setattr(api, "_user32", lambda: _fake_user32(SendInput=lambda *a: 0))
    with pytest.raises(OSError, match="SendInput"):
        api._send_vk(api._VK["enter"])
