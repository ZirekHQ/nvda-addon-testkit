"""Investigation for issue #34, gaps 2 & 5: does a queued main-thread job
start while a real ShowModal() dialog is up?

This is not a regression test. It is a one-shot probe: run it once on
Windows CI, read the result, and act on it per the plan (either open a new
issue describing a real fix, or proceed with the simulate_modal() fallback
in the next task). Delete or keep this file once the investigation is
resolved -- it is not meant to run on every CI build.
"""


def test_a_second_job_while_a_real_modal_is_up(nvda, require_eval):
    show_dialog = (
        "import threading\n"
        "import wx\n"
        "started = threading.Event()\n"
        "def show():\n"
        "    started.set()\n"
        "    dlg = wx.MessageDialog(None, 'probe', 'probe', wx.YES_NO)\n"
        "    wx.CallLater(3000, dlg.EndModal, wx.ID_YES)\n"
        "    dlg.ShowModal()\n"
        "    dlg.Destroy()\n"
        "threading.Thread(target=show).start()\n"
        "started.wait(timeout=5)\n"
    )
    nvda.exec(show_dialog)

    # While the dialog above is presumed to be showing, queue a trivial
    # second job with a short timeout and see whether it ever starts.
    try:
        nvda.exec("__result__ = 1 + 1")
        second_job_started = True
    except Exception as error:
        second_job_started = "never started" not in str(error)

    assert second_job_started, (
        "CONFIRMS THE DEADLOCK: a second main-thread job never started while "
        "a real ShowModal() dialog was up. Proceed with Task 7 (the "
        "simulate_modal() fallback)."
    )
    # If this assertion passes instead, the queue is NOT blocked by ShowModal()
    # in this NVDA version: STOP, do not proceed to Task 7, and open a new
    # issue describing this finding plus what actually blocks input_api.py's
    # keys_press() from dismissing the dialog (if anything still does).
