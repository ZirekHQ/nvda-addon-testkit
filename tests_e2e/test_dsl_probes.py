"""Probes for DSL behaviour not yet verified on real NVDA."""

import pytest

DIALOG = (
    "import wx\n"
    "dlg = wx.MessageDialog(None, 'confirm?', 'confirm?', wx.YES_NO)\n"
    "dlg.ShowModal()\n"
    "dlg.Destroy()\n"
)


def test_speech_and_log_reads_work_while_a_modal_is_open(require_eval, nvda):
    nvda.open_dialog(DIALOG)
    try:
        assert isinstance(nvda.speech.index(), int)
        assert isinstance(nvda.log.all(), list)
    finally:
        nvda.close_dialog("enter")


@pytest.mark.parametrize("text", ["Hello", "a.b,c", "x!y"])
def test_typing_characters_beyond_lowercase_letters(nvda, text):
    nvda.type(text)


@pytest.mark.xfail(strict=False, reason="non-ASCII gesture names are unverified")
def test_typing_non_ascii_characters(nvda):
    nvda.type("ünï")
