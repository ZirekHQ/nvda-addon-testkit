import xmlrpc.client

import pytest


@pytest.fixture
def api(event_queue, monkeypatch):
    from nvda_testkit_spy import eval_api, modal_api

    monkeypatch.setattr(modal_api, "_foreground_owner", lambda: (100, 42))
    return eval_api


def test_it_is_registered_under_the_name_the_host_calls(event_queue):
    from nvda_testkit_spy import eval_api  # noqa: F401  -- importing is what registers it
    from nvda_testkit_spy.registry import METHODS

    assert "eval_in_nvda" in METHODS


def test_it_evaluates_an_expression(api):
    assert api.eval_in_nvda("1 + 1") == 2


def test_it_has_real_builtins(api):
    assert api.eval_in_nvda("len([1, 2, 3])") == 3


def test_it_can_reach_nvda_modules(api):
    assert api.eval_in_nvda("__import__('config').conf['speech']['synth']") == "espeak"


def test_an_unmarshallable_result_becomes_its_repr(api):
    result = api.eval_in_nvda("object")
    assert isinstance(result, str)
    xmlrpc.client.dumps((result,), allow_none=True)


def test_containers_are_flattened_into_something_xmlrpc_can_carry(api):
    result = api.eval_in_nvda("{'a': [1, object]}")
    assert result["a"][0] == 1
    assert isinstance(result["a"][1], str)
    xmlrpc.client.dumps((result,), allow_none=True)


def test_a_raising_expression_propagates(api):
    with pytest.raises(ZeroDivisionError):
        api.eval_in_nvda("1 / 0")


def test_exec_it_is_registered_under_the_name_the_host_calls(event_queue):
    from nvda_testkit_spy import eval_api  # noqa: F401
    from nvda_testkit_spy.registry import METHODS

    assert "exec_in_nvda" in METHODS


def test_exec_runs_multiple_statements(api):
    result = api.exec_in_nvda("x = 1\ny = 2\n__result__ = x + y")
    assert result == 3


def test_exec_without_a_result_binding_returns_none(api):
    assert api.exec_in_nvda("x = 1") is None


def test_exec_has_real_builtins_and_imports(api):
    result = api.exec_in_nvda("import math\n__result__ = math.floor(3.7)")
    assert result == 3


def test_exec_a_syntax_error_raises_syntaxerror(api):
    with pytest.raises(SyntaxError):
        api.exec_in_nvda("def broken(:\n    pass")


def test_exec_a_nested_function_can_see_top_level_names(api):
    result = api.exec_in_nvda(
        "vals = [1, 2, 3]\ndef total():\n    return sum(vals)\n__result__ = total()"
    )
    assert result == 6


def test_exec_a_runtime_error_propagates(api):
    with pytest.raises(ZeroDivisionError):
        api.exec_in_nvda("__result__ = 1 / 0")


def test_nowait_it_is_registered_under_the_name_the_host_calls(event_queue):
    from nvda_testkit_spy import eval_api  # noqa: F401
    from nvda_testkit_spy.registry import METHODS

    assert "exec_in_nvda_nowait" in METHODS


def test_nowait_returns_true_without_waiting_for_the_result(api):
    assert api.exec_in_nvda_nowait("x = 1") is True


def test_nowait_does_not_run_the_scenario_inline(api, event_queue, capsys):
    event_queue.auto_drain = False
    api.exec_in_nvda_nowait("print('ran')")
    assert capsys.readouterr().out == ""
    event_queue.drain()
    assert capsys.readouterr().out == "ran\n"


def test_nowait_a_syntax_error_raises_synchronously_not_once_queued(api, event_queue):
    event_queue.auto_drain = False
    with pytest.raises(SyntaxError):
        api.exec_in_nvda_nowait("def broken(:\n    pass")
    assert event_queue.empty()


def test_nowait_a_runtime_error_is_logged_instead_of_raised(api):
    import logHandler

    logHandler.log.reset_mock()
    api.exec_in_nvda_nowait("1 / 0")
    logHandler.log.error.assert_called_once()


def test_nowait_records_the_foreground_baseline_before_queueing(api, event_queue, monkeypatch):
    event_queue.auto_drain = False
    order = []
    monkeypatch.setattr(api, "remember_foreground_baseline", lambda: order.append("baseline"))
    monkeypatch.setattr(api.queueHandler, "queueFunction", lambda q, fn: order.append("queued"))
    api.exec_in_nvda_nowait("x = 1")
    assert order == ["baseline", "queued"]
