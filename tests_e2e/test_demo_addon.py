"""The real thing: install an add-on into a real NVDA and prove it works."""

import re

import pytest

from nvda_testkit.namespaces.addons import AddonState

SPOKEN_PHRASE = "testkit demo says hello"
STARTUP_MESSAGE = "testkit demo add-on loaded"


@pytest.fixture
def addon_under_test(nvda_session, built_demo_addon):
    """Overrides the session-scoped plugin fixture so no test inherits another's install.

    Every test here starts and ends with the demo add-on not installed.
    """
    nvda_session.addons.install(built_demo_addon)
    nvda_session.restart_harness()
    yield built_demo_addon
    state = nvda_session.addons.state("testkit-demo")
    if state is not AddonState.NOT_INSTALLED:
        if state is not AddonState.PENDING_REMOVE:
            nvda_session.addons.remove("testkit-demo")
        nvda_session.restart_harness()


@pytest.mark.fresh_nvda
def test_install_is_two_phase_and_completes_on_restart(
    nvda, built_demo_addon, assert_no_unexpected_errors
):
    """Owns the install lifecycle end to end, so it does not use addon_under_test."""
    # tag::addons[]
    assert nvda.addons.state("testkit-demo") is AddonState.NOT_INSTALLED

    info = nvda.addons.install(built_demo_addon)
    assert info.name == "testkit-demo"
    assert nvda.addons.state("testkit-demo") is AddonState.PENDING_INSTALL

    nvda.restart_harness()
    assert nvda.addons.state("testkit-demo") is AddonState.ENABLED
    assert_no_unexpected_errors(nvda)

    nvda.addons.remove("testkit-demo")
    nvda.restart_harness()
    assert nvda.addons.state("testkit-demo") is AddonState.NOT_INSTALLED
    # end::addons[]


def test_the_installed_addon_logs_at_startup(nvda, addon_under_test):
    # tag::log[]
    nvda.restart_harness()
    nvda.log.wait_for(re.escape(STARTUP_MESSAGE), since=0, timeout=20)
    # end::log[]


def test_its_gesture_produces_the_expected_speech(nvda, addon_under_test):
    before = nvda.speech.index()
    nvda.keys.press("NVDA+shift+control+d")
    found = nvda.speech.wait_for(SPOKEN_PHRASE, timeout=20, since=before)
    assert SPOKEN_PHRASE in found.text


def test_it_survives_a_restart(nvda, addon_under_test):
    # tag::fixtures[]
    nvda.restart_harness()
    assert nvda.addons.state("testkit-demo") is AddonState.ENABLED
    before = nvda.speech.index()
    nvda.keys.press("NVDA+shift+control+d")
    nvda.speech.wait_for(SPOKEN_PHRASE, timeout=20, since=before)
    # end::fixtures[]


def test_removal_is_also_two_phase(nvda, addon_under_test):
    nvda.addons.remove("testkit-demo")
    assert nvda.addons.state("testkit-demo") is AddonState.PENDING_REMOVE
    nvda.restart_harness()
    assert nvda.addons.state("testkit-demo") is AddonState.NOT_INSTALLED
