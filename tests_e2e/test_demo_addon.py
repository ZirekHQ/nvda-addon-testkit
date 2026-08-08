"""The real thing: install an add-on into a real NVDA and prove it works."""

import pytest

from nvda_testkit.namespaces.addons import AddonState

SPOKEN_PHRASE = "testkit demo says hello"
STARTUP_MESSAGE = "testkit demo add-on loaded"


@pytest.mark.fresh_nvda
def test_install_is_two_phase_and_completes_on_restart(nvda, built_demo_addon):
    """Owns the install lifecycle end to end, and leaves NVDA as it found it.

    This test deliberately does NOT use addon_under_test: that fixture is
    session-scoped and installs the same add-on, so the two would collide.
    Cleaning up here is what lets the rest of the file rely on the fixture.
    """
    assert nvda.addons.state("testkit-demo") is AddonState.NOT_INSTALLED

    info = nvda.addons.install(built_demo_addon)
    assert info.name == "testkit-demo"
    assert nvda.addons.state("testkit-demo") is AddonState.PENDING_INSTALL

    nvda.restart()
    assert nvda.addons.state("testkit-demo") is AddonState.ENABLED
    nvda.log.assert_no_errors()

    nvda.addons.remove("testkit-demo")
    nvda.restart()
    assert nvda.addons.state("testkit-demo") is AddonState.NOT_INSTALLED


def test_the_installed_addon_logs_at_startup(nvda, addon_under_test):
    # The nvda fixture's reset() clears the log, so restart here and read the
    # fresh process's startup output before anything else can clear it.
    nvda.restart()
    messages = [record.message for record in nvda.log.all()]
    assert any(STARTUP_MESSAGE in message for message in messages), (
        f"expected {STARTUP_MESSAGE!r} in NVDA's log; got {messages[-20:]}"
    )


def test_its_gesture_produces_the_expected_speech(nvda, addon_under_test):
    before = nvda.speech.index()
    nvda.keys.press("NVDA+shift+control+d")
    found = nvda.speech.wait_for(SPOKEN_PHRASE, timeout=20, since=before)
    assert SPOKEN_PHRASE in found.text


def test_it_survives_a_restart(nvda, addon_under_test):
    nvda.restart()
    assert nvda.addons.state("testkit-demo") is AddonState.ENABLED
    before = nvda.speech.index()
    nvda.keys.press("NVDA+shift+control+d")
    nvda.speech.wait_for(SPOKEN_PHRASE, timeout=20, since=before)


def test_removal_is_also_two_phase(nvda, addon_under_test):
    """Must stay last in this file: it uninstalls what addon_under_test set up,
    and that session-scoped fixture will not reinstall it."""
    nvda.addons.remove("testkit-demo")
    assert nvda.addons.state("testkit-demo") is AddonState.PENDING_REMOVE
    nvda.restart()
    assert nvda.addons.state("testkit-demo") is AddonState.NOT_INSTALLED
