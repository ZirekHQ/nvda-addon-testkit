import xmlrpc.client

import pytest


@pytest.fixture
def api(event_queue):
    from nvda_testkit_spy import eval_api

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
