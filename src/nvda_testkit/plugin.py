"""The pytest plugin. Registered automatically via the pytest11 entry point."""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

from .client import NvdaClient
from .dsl import Nvda
from .errors import ProvisionError
from .provisioning import Provisioned, provision, provision_fake
from .settings import TestkitSettings, load_settings


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
        "--nvda-verbose",
        action="store_true",
        default=None,
        help="do not truncate long lists in DSL failure messages",
    )
    group.addoption(
        "--nvda-fake",
        default=None,
        help="drive the FakeNvda double at this path instead of a real NVDA (development only)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "fresh_nvda: restart NVDA before this test")


def _worker_count(config: pytest.Config) -> int:
    worker_input = getattr(config, "workerinput", None)
    if isinstance(worker_input, dict):
        return int(worker_input.get("workercount", 1))
    workers = getattr(config.option, "numprocesses", None)
    return workers if isinstance(workers, int) else 1


def _refuse_parallel_nvda(config: pytest.Config) -> None:
    workers = _worker_count(config)
    if workers > 1:
        raise ProvisionError(
            f"nvda-addon-testkit cannot run in parallel: -n {workers} was requested, but only "
            "one NVDA can own a desktop session. Shard across CI jobs instead."
        )


def _flag(enabled: object) -> bool | None:
    return True if enabled else None


@pytest.fixture(scope="session")
def nvda_settings(pytestconfig: pytest.Config) -> TestkitSettings:
    option = pytestconfig.option
    return load_settings(
        overrides={
            "channel": option.nvda_version or option.nvda_channel,
            "timeout_scale": option.nvda_timeout_scale,
            "allow_eval": _flag(option.nvda_allow_eval),
            "keep_portable": _flag(option.nvda_keep_portable),
            "out_dir": option.nvda_out_dir,
            "verbose": _flag(option.nvda_verbose),
        }
    )


@pytest.fixture(scope="session")
def _nvda_provisioned(
    nvda_settings: TestkitSettings, pytestconfig: pytest.Config
) -> Iterator[Provisioned]:
    _refuse_parallel_nvda(pytestconfig)
    fake = pytestconfig.option.nvda_fake
    running: Provisioned = (
        provision_fake(nvda_settings, Path(fake)) if fake else provision(nvda_settings)
    )
    try:
        yield running
    finally:
        running.teardown()


@pytest.fixture(scope="session")
def nvda_session(_nvda_provisioned: Provisioned, nvda_settings: TestkitSettings) -> NvdaClient:
    client = NvdaClient(_nvda_provisioned.process, _nvda_provisioned.rpc, settings=nvda_settings)
    _nvda_provisioned.current_rpc = lambda: client.rpc
    return client


@pytest.fixture
def nvda(request: pytest.FixtureRequest, nvda_session: NvdaClient) -> Iterator[Nvda]:
    dsl = Nvda(nvda_session, bundle=lambda: request.getfixturevalue("addon_bundle"))
    try:
        if request.node.get_closest_marker("fresh_nvda"):
            nvda_session.restart_harness()
        nvda_session.reset()
        yield dsl
    finally:
        dsl.finish()


@pytest.fixture(autouse=True)
def nvda_reset(request: pytest.FixtureRequest) -> Iterator[None]:
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
        warnings.warn(
            f"nvda-testkit: reset() failed during teardown: {error}",
            stacklevel=2,
        )


@pytest.fixture(scope="session")
def addon_bundle(nvda_settings: TestkitSettings) -> Path:
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
    nvda_session.addons.install(addon_bundle)
    nvda_session.restart_harness()
    return addon_bundle
