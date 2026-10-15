def test_speech_and_log_reads_work_while_a_modal_is_open(require_eval, nvda, confirm_dialog_source):
    nvda.open_dialog(confirm_dialog_source)
    try:
        assert isinstance(nvda.speech.index(), int)
        assert isinstance(nvda.log.all(), list)
    finally:
        nvda.close_dialog("enter")
