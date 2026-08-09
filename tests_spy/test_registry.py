import pytest


def test_rpc_method_registers_by_name():
    from nvda_testkit_spy import registry

    @registry.rpc_method
    def sample_method():
        return 42

    assert registry.METHODS["sample_method"] is sample_method


def test_dispatch_requires_the_token_as_the_first_argument():
    from nvda_testkit_spy import registry

    dispatcher = registry.Dispatcher("secret")
    with pytest.raises(Exception, match="AUTH: first argument"):
        dispatcher._dispatch("ping", ())


def test_dispatch_rejects_a_wrong_token():
    from nvda_testkit_spy import registry

    dispatcher = registry.Dispatcher("secret")
    with pytest.raises(Exception, match="AUTH: token rejected"):
        dispatcher._dispatch("ping", ("wrong",))


def test_dispatch_rejects_an_unknown_method_before_checking_anything_else():
    from nvda_testkit_spy import registry

    dispatcher = registry.Dispatcher("secret")
    with pytest.raises(Exception, match="UNKNOWN: no such method"):
        dispatcher._dispatch("nope", ("secret",))


def test_dispatch_forwards_remaining_arguments():
    from nvda_testkit_spy import registry

    @registry.rpc_method
    def add_up(a, b):
        return a + b

    dispatcher = registry.Dispatcher("secret")
    assert dispatcher._dispatch("add_up", ("secret", 2, 3)) == 5


def test_a_handler_exception_is_reported_with_its_type():
    from nvda_testkit_spy import registry

    @registry.rpc_method
    def explode():
        raise ValueError("boom")

    dispatcher = registry.Dispatcher("secret")
    with pytest.raises(Exception, match="ValueError: boom"):
        dispatcher._dispatch("explode", ("secret",))
