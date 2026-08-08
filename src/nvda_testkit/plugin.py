"""The pytest plugin. Registered automatically via the pytest11 entry point."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from .client import NvdaClient
from .errors import ProvisionError
from .provisioning import Provisioned, provision, provision_fake
from .settings import load_settings


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("nvda-testkit", "NVDA add-on end-to-end testing")
    group.addoption("--nvda-channel", default=None, help="stable, beta, alpha, or a pinned version")
    group.addoption("--nvda-version", default=None, help="alias for --nvda-channel <version>")
    group.addoption("--nvda-timeout-scale", type=float, default=None, help="multiply every timeout")
    group.addoption("--nvda-allow-eval", action="store_true", default=None, help="enable nvda.eval")
    group.addoption(
        "--nvda-keep-portable",
        action="store_true",
        default=None,
        help="do not delete the portable NVDA copy on teardown",
    )
    group.addoption("--nvda-out-dir", default=None, help="where logs and artifacts are written")
    group.addoption(
        "--nvda-fake",
        default=None,
        help="drive the FakeNvda double at this path instead of a real NVDA (development only)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "fresh_nvda: restart NVDA before this test")

    # Only one NVDA can own a desktop session, so parallel workers would fight
    # over it and produce results that mean nothing.
    workers = getattr(config.option, "numprocesses", None)
    if isinstance(workers, int) and workers > 1:
        raise pytest.UsageError(
            f"nvda-addon-testkit cannot run in parallel: -n {workers} was requested, but only "
            "one NVDA can own a desktop session. Shard across CI jobs instead."
        )


@pytest.fixture(scope="session")
def nvda_settings(pytestconfig: pytest.Config):
    option = pytestconfig.option
    return load_settings(
        overrides={
            "channel": option.nvda_version or option.nvda_channel,
            "timeout_scale": option.nvda_timeout_scale,
            "allow_eval": True if option.nvda_allow_eval else None,
            "keep_portable": True if option.nvda_keep_portable else None,
            "out_dir": option.nvda_out_dir,
        }
    )


@pytest.fixture(scope="session")
def _nvda_provisioned(nvda_settings, pytestconfig: pytest.Config):
    fake = pytestconfig.option.nvda_fake
    running: Provisioned = (
        provision_fake(nvda_settings, Path(fake)) if fake else provision(nvda_settings)
    )
    try:
        yield running
    finally:
        running.teardown()


@pytest.fixture(scope="session")
def nvda_session(_nvda_provisioned, nvda_settings) -> NvdaClient:
    return NvdaClient(_nvda_provisioned.process, _nvda_provisioned.rpc, settings=nvda_settings)


@pytest.fixture
def nvda(request: pytest.FixtureRequest, nvda_session: NvdaClient) -> NvdaClient:
    if request.node.get_closest_marker("fresh_nvda"):
        nvda_session.restart()
    nvda_session.reset()
    return nvda_session


@pytest.fixture(autouse=True)
def nvda_reset(request: pytest.FixtureRequest):
    """Reset after any test that touched NVDA, so the next one starts clean.

    Autouse, but deliberately lazy: a test that never asks for `nvda` never
    causes NVDA to start.
    """
    yield
    if "nvda_session" not in request.fixturenames:
        return
    client = request.getfixturevalue("nvda_session")
    try:
        client.reset()
    except Exception as error:
        # Non-fatal here -- the next test's `nvda` fixture calls reset() again
        # and will surface a persistent failure -- but never silent: if this
        # is the last test in the session, a warning is the only channel left.
        warnings.warn(
            f"nvda-testkit: reset() failed during teardown: {error}",
            stacklevel=2,
        )


@pytest.fixture(scope="session")
def addon_bundle(nvda_settings) -> Path:
    pattern = nvda_settings.addon_bundle
    if not pattern:
        raise ProvisionError(
            "No add-on bundle configured. Set addon-bundle under [tool.nvda-testkit] "
            'in pyproject.toml, e.g. addon-bundle = "dist/my-addon-*.nvda-addon".'
        )
    matches = sorted(Path().glob(pattern.replace("{version}", "*")))
    if not matches:
        raise ProvisionError(
            f"No add-on bundle matched {pattern!r} from {Path().resolve()}. Build it first."
        )
    if len(matches) > 1:
        raise ProvisionError(
            f"{pattern!r} matched {len(matches)} bundles: {[str(m) for m in matches]}. "
            "Clean the stale ones out, or pin the pattern."
        )
    return matches[0]


@pytest.fixture(scope="session")
def addon_under_test(nvda_session: NvdaClient, addon_bundle: Path) -> Path:
    """The bundle, installed and enabled, with NVDA restarted to complete it."""
    nvda_session.rpc.call("addons_install", str(addon_bundle.resolve()))
    nvda_session.restart()
    return addon_bundle
