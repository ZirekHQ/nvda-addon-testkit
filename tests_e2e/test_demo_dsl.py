"""The demo add-on driven through the DSL. Each tagged block is a docs example.

This file assumes the demo add-on is not installed when it starts: test_demo_addon.py,
sorted earlier, uninstalls it last.
"""

import pytest

# Mirrors RUNNER_ENVIRONMENT_ERRORS in tests_e2e/conftest.py.
RUNNER_NOISE = (
    r"nvwave|WASAPI|audio (?:device|output|session|endpoint)",
    r"synthDriver|synthesi[sz]|espeak|oneCore|SAPI",
    r"braille ?display|brailleDisplayDriver|brailleInput",
    r"UIAHandler|IAccessible|interactive desktop|desktop object",
)


@pytest.mark.fresh_nvda
def test_install_and_remove_are_one_step_each(nvda):
    # tag::dsl-lifecycle[]
    nvda.should_have_addon("testkit-demo", "not installed")
    nvda.install_addon()
    nvda.should_have_addon("testkit-demo", "enabled")
    nvda.remove_addon("testkit-demo")
    nvda.should_have_addon("testkit-demo", "not installed")
    # end::dsl-lifecycle[]


def test_the_gesture_announces_the_phrase(nvda):
    nvda.install_addon()
    # tag::dsl-basic[]
    nvda.press("NVDA+shift+control+d")
    nvda.should_hear("testkit demo says hello")
    # end::dsl-basic[]


def test_startup_logs_the_loaded_message(nvda):
    nvda.install_addon()
    nvda.relaunch()
    nvda.should_log("testkit demo add-on loaded", within=20)
    nvda.should_have_no_errors(ignoring=list(RUNNER_NOISE))


def test_the_block_form_waits_for_the_speech_a_step_causes(nvda):
    nvda.install_addon()
    # tag::dsl-expecting[]
    with nvda.expecting_speech("testkit demo says hello"):
        nvda.press("NVDA+shift+control+d")
    # end::dsl-expecting[]


def test_a_real_dialog_opens_and_closes_in_a_block(require_eval, nvda):
    # tag::dsl-dialog[]
    with nvda.dialog(
        "import wx\n"
        "dlg = wx.MessageDialog(None, 'confirm?', 'confirm?', wx.YES_NO)\n"
        "dlg.ShowModal()\n"
        "dlg.Destroy()\n",
        close_with="enter",
    ):
        pass
    # end::dsl-dialog[]
    nvda.wait_until_idle(timeout=15)
