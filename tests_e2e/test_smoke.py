"""The narrowest possible proof that a real NVDA started and is answering."""


def test_nvda_is_running_and_reports_its_version(nvda):
    version = nvda.version
    assert version.version, "NVDA reported no version"
    assert version.api_version, "NVDA reported no add-on API version"


def test_nvda_reaches_idle(nvda):
    nvda.wait_until_idle(timeout=30)


def test_nvda_speaks_when_asked(nvda):
    # speak() is synchronous, so the speech is already recorded by the time
    # wait_for() would otherwise start looking. Capture the index first.
    before = nvda.speech.index()
    nvda.speech.speak("the quick brown fox")
    found = nvda.speech.wait_for("quick brown fox", timeout=20, since=before)
    assert "quick brown fox" in found.text


def test_a_gesture_reaches_nvda(nvda):
    nvda.keys.press("NVDA+shift+control+F12")
    # sent() accumulates across the whole session -- reset() does not clear it,
    # because the replay trace wants the full history. So check membership, not
    # equality, or this becomes order-dependent.
    assert "NVDA+shift+control+F12" in [entry["gesture"] for entry in nvda.keys.sent()]


def test_config_round_trips_through_a_real_nvda(nvda):
    original = nvda.config.get(("speech", "synth"))
    assert isinstance(original, str)
    snapshot = nvda.config.snapshot()
    assert "speech" in snapshot


def test_startup_produced_no_errors(nvda, assert_no_unexpected_errors):
    # The nvda fixture's reset() clears the log before this body runs, so without
    # a restart here there would be no startup left to assert anything about.
    nvda.restart()
    assert_no_unexpected_errors(nvda)
