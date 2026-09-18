"""Investigation for issue #34, gaps 2 & 5: does a queued main-thread job
start while a real ShowModal() dialog is up?

This is not a regression test. It is a one-shot probe: run it once on
Windows CI, read the result, and act on it per the plan (either open a new
issue describing a real fix, or proceed with the simulate_modal() fallback
in the next task). Delete or keep this file once the investigation is
resolved -- it is not meant to run on every CI build.

Everything happens inside a single exec_in_nvda call, entirely on NVDA's
main thread: the spy's XML-RPC server (server.py) is a plain, unthreaded
SimpleXMLRPCServer, so two separate RPC connections can never be genuinely
concurrent at the transport level -- the second call simply can't be
dispatched until the first's handler returns. Queuing the second job from
*inside* the running scenario, via queueHandler.queueFunction directly,
avoids needing RPC-level concurrency at all: it tests whether NVDA's own
queue-draining mechanism still runs while the main thread is nested inside
ShowModal()'s event loop, using a timestamp comparison instead of a second
network round trip.

A third, lower-probability outcome is possible: if the dialog's own
wx.CallLater dismiss timer never fires for some unrelated reason, this
scenario never returns from ShowModal(), so nvda.exec() raises an RpcError
(wrapping exec_in_nvda's server-side "started on NVDA's main thread but did
not return within 30.0s" timeout) instead of returning a __result__ to
assert on. If you see that on a real run, it's worth investigating
separately -- it doesn't confirm or refute the queue-blocking hypothesis
either way.
"""


def test_a_second_job_while_a_real_modal_is_up(require_eval, nvda):
    scenario = (
        "import queueHandler\n"
        "import time\n"
        "import wx\n"
        "job_b_ran_at = []\n"
        # exec_in_nvda runs this with separate globals/locals dicts (like a
        # class body), so a nested def can't see job_b_ran_at/time as
        # globals -- bind both as defaults, evaluated now, in this scope.
        "def job_b(sink=job_b_ran_at, now=time.monotonic):\n"
        "    sink.append(now())\n"
        "queueHandler.queueFunction(queueHandler.eventQueue, job_b)\n"
        "dlg = wx.MessageDialog(None, 'probe', 'probe', wx.YES_NO)\n"
        "wx.CallLater(1000, dlg.EndModal, wx.ID_YES)\n"
        "before = time.monotonic()\n"
        "dlg.ShowModal()\n"
        "after = time.monotonic()\n"
        "dlg.Destroy()\n"
        "__result__ = {\n"
        "    'ran_during_modal': bool(job_b_ran_at) and before <= job_b_ran_at[0] <= after,\n"
        "    'ran_at_all': bool(job_b_ran_at),\n"
        "}\n"
    )

    result = nvda.exec(scenario)

    assert result["ran_during_modal"], (
        "CONFIRMS THE DEADLOCK: a second main-thread job never ran while a "
        f"real ShowModal() dialog was up (ran_at_all={result['ran_at_all']!r}). "
        "Proceed with Task 7 (the simulate_modal() fallback)."
    )
    # If this assertion passes instead, the queue IS drained during
    # ShowModal() in this NVDA version: STOP, do not proceed to Task 7, and
    # open a new issue describing this finding plus what actually blocks
    # input_api.py's keys_press() from dismissing the dialog (if anything
    # still does).
