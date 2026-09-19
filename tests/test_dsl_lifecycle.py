from pathlib import Path

import pytest

from nvda_testkit.dsl import Nvda
from nvda_testkit.errors import TestkitError


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
    with pytest.raises(TestkitError, match="addon-bundle"):
        Nvda(make_client()).install_addon()


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
    with pytest.raises(AssertionError, match="Expected add-on demo-addon to be enabled"):
        nvda.should_have_addon("demo-addon", "enabled")


def test_an_unknown_state_lists_the_valid_ones(make_client):
    with pytest.raises(ValueError, match="pending install"):
        Nvda(make_client()).should_have_addon("demo-addon", "sleeping")


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
