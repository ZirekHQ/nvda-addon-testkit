from pathlib import Path

import pytest

from nvda_testkit.dsl import Nvda
from nvda_testkit.dsl.lifecycle import parse_state
from nvda_testkit.errors import RpcError, TestkitError
from nvda_testkit.namespaces.addons import AddonState


@pytest.fixture
def bundle(tmp_path):
    path = tmp_path / "demo.nvda-addon"
    path.write_bytes(b"")
    return path


def test_install_addon_completes_the_two_phases(make_client, bundle):
    nvda = Nvda(make_client(), bundle=lambda: bundle)
    nvda.install_addon()
    nvda.should_have_addon("demo-addon", "enabled")


def test_an_explicit_path_wins_over_the_default_bundle(make_client, bundle):
    nvda = Nvda(make_client(), bundle=lambda: Path("missing.nvda-addon"))
    nvda.install_addon(bundle)
    nvda.should_have_addon("demo-addon", "enabled")


def test_without_a_bundle_the_step_explains_what_is_missing(make_client):
    nvda = Nvda(make_client())
    with pytest.raises(TestkitError, match="addon-bundle"):
        nvda.install_addon()


def test_remove_addon_completes_the_two_phases(make_client, bundle):
    nvda = Nvda(make_client(), bundle=lambda: bundle)
    nvda.install_addon()
    nvda.remove_addon("demo-addon")
    nvda.should_have_addon("demo-addon", "not installed")


def test_should_have_addon_accepts_spaced_lowercase_states(make_client, bundle):
    nvda = Nvda(make_client(), bundle=lambda: bundle)
    nvda.addons.install(bundle)
    nvda.should_have_addon("demo-addon", "pending install")


def test_should_have_addon_reports_actual_and_expected_state(make_client):
    nvda = Nvda(make_client())
    with pytest.raises(AssertionError, match="to be enabled, but it is not installed"):
        nvda.should_have_addon("demo-addon", "enabled")


def test_an_unknown_state_lists_the_valid_ones(make_client):
    nvda = Nvda(make_client())
    with pytest.raises(ValueError, match="pending install"):
        nvda.should_have_addon("demo-addon", "sleeping")


def test_finish_removes_what_the_test_installed(make_client, bundle):
    nvda = Nvda(make_client(), bundle=lambda: bundle)
    nvda.install_addon()
    nvda.finish()
    nvda.should_have_addon("demo-addon", "not installed")


def test_finish_leaves_addons_installed_outside_the_dsl_alone(make_client, bundle):
    nvda = Nvda(make_client(), bundle=lambda: bundle)
    nvda.addons.install(bundle)
    nvda.relaunch(timeout=20)
    nvda.finish()
    nvda.should_have_addon("demo-addon", "enabled")


def test_finish_checks_the_log_before_the_undo_relaunch_clears_it(make_client, bundle):
    nvda = Nvda(make_client(fail_on_log_errors=True), bundle=lambda: bundle)
    nvda.install_addon()
    nvda.rpc.call("log_emit", "ERROR", "boom")
    with pytest.raises(AssertionError, match="unexpected error"):
        nvda.finish()
    nvda.should_have_addon("demo-addon", "not installed")


def test_a_failed_restart_during_install_still_leaves_an_undo(make_client, bundle):
    nvda = Nvda(make_client(), bundle=lambda: bundle)
    real = nvda.client.restart_harness
    calls = []

    def flaky(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RpcError("boom")
        real(**kwargs)

    nvda.client.restart_harness = flaky
    with pytest.raises(RpcError):
        nvda.install_addon()
    nvda.finish()
    nvda.should_have_addon("demo-addon", "not installed")


def test_a_failing_undo_is_not_retried_by_a_second_finish(make_client, bundle):
    nvda = Nvda(make_client(), bundle=lambda: bundle)
    nvda.install_addon()

    def broken(name):
        raise RpcError("boom")

    nvda.client.addons.remove = broken
    with pytest.raises(AssertionError, match="RpcError: boom") as raised:
        nvda.finish()
    assert isinstance(raised.value.__cause__, RpcError)
    nvda.finish()


@pytest.mark.parametrize(
    "spelled",
    [AddonState.PENDING_INSTALL, "pending_install", "Pending Install", "PENDING_INSTALL"],
)
def test_parse_state_accepts_members_underscores_and_any_case(spelled):
    assert parse_state(spelled) is AddonState.PENDING_INSTALL


def test_parse_state_accepts_mixed_case_single_words():
    assert parse_state("Enabled") is AddonState.ENABLED
