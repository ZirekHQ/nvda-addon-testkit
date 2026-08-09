from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

FAKE = Path(__file__).parent / "fake_nvda.py"


@pytest.fixture
def harness(pytester):
    """A pytester project wired to drive the FakeNvda double."""
    pytester.makeini(
        f"""
        [pytest]
        addopts = --nvda-fake={FAKE.as_posix()}
        """
    )
    return pytester


def test_the_nvda_fixture_yields_a_connected_client(harness):
    harness.makepyfile(
        """
        def test_connected(nvda):
            assert nvda.version.version == "2026.1.1"
            assert nvda.speech.index() == 0
        """
    )
    harness.runpytest().assert_outcomes(passed=1)


def test_state_does_not_leak_between_tests(harness):
    harness.makepyfile(
        """
        def test_makes_noise(nvda):
            nvda.speech.speak("noise from the first test")
            assert nvda.speech.index() == 1

        def test_starts_clean(nvda):
            assert nvda.speech.index() == 0, "the autouse reset should have cleared this"
        """
    )
    harness.runpytest().assert_outcomes(passed=2)


def test_config_changes_are_rolled_back_between_tests(harness):
    harness.makepyfile(
        """
        def test_changes_config(nvda):
            nvda.config.set(("speech", "synth"), "changed")

        def test_sees_the_baseline(nvda):
            assert nvda.config.get(("speech", "synth")) == "espeak"
        """
    )
    harness.runpytest().assert_outcomes(passed=2)


def test_the_same_nvda_process_is_reused_across_tests(harness):
    harness.makepyfile(
        """
        PIDS = []

        def test_one(nvda):
            PIDS.append(nvda.process.handshake.pid)

        def test_two(nvda):
            PIDS.append(nvda.process.handshake.pid)
            assert PIDS[0] == PIDS[1], "NVDA should start once per session"
        """
    )
    harness.runpytest().assert_outcomes(passed=2)


def test_fresh_nvda_marker_restarts_the_process(harness):
    harness.makepyfile(
        """
        import pytest

        PIDS = []

        def test_one(nvda):
            PIDS.append(nvda.process.handshake.pid)

        @pytest.mark.fresh_nvda
        def test_two(nvda):
            assert nvda.process.handshake.pid != PIDS[0]
        """
    )
    harness.runpytest().assert_outcomes(passed=2)


def test_eval_is_off_by_default_and_on_with_the_flag(harness):
    harness.makepyfile(
        """
        import pytest
        from nvda_testkit.errors import TestkitError

        def test_refused(nvda):
            with pytest.raises(TestkitError):
                nvda.eval("1 + 1")
        """
    )
    harness.runpytest().assert_outcomes(passed=1)

    harness.makepyfile(
        """
        def test_allowed(nvda):
            assert nvda.eval("6 * 7") == 42
        """
    )
    harness.runpytest("--nvda-allow-eval").assert_outcomes(passed=1)


def test_timeout_scale_reaches_the_client(harness):
    harness.makepyfile(
        """
        def test_scaled(nvda):
            assert nvda.rpc.timeout_scale == 3.0
        """
    )
    harness.runpytest("--nvda-timeout-scale=3.0").assert_outcomes(passed=1)


def test_xdist_with_several_workers_is_refused(harness):
    pytest.importorskip("xdist")
    harness.makepyfile(
        """
        def test_anything(nvda):
            pass
        """
    )
    result = harness.runpytest("-n", "2")
    result.stderr.fnmatch_lines(["*nvda-addon-testkit cannot run in parallel*"])
    assert result.ret != 0


def test_xdist_with_a_single_worker_is_allowed(harness):
    pytest.importorskip("xdist")
    harness.makepyfile(
        """
        def test_anything(nvda):
            assert nvda.speech.index() == 0
        """
    )
    harness.runpytest("-n", "1").assert_outcomes(passed=1)


def test_a_test_that_does_not_ask_for_nvda_never_starts_it(harness):
    # Patched on `plugin`, not `provisioning`: plugin.py imports the name
    # directly (`from .provisioning import ... provision_fake`), so it is
    # bound in plugin's own module globals by the time this conftest runs.
    # Patching `provisioning.provision_fake` would leave that binding alone
    # and the spy would never be called.
    harness.makeconftest(
        """
        import pathlib
        from nvda_testkit import plugin

        _MARKER = pathlib.Path(__file__).parent / "provisioned.marker"
        _real = plugin.provision_fake

        def _spy(*args, **kwargs):
            _MARKER.write_text("started")
            return _real(*args, **kwargs)

        plugin.provision_fake = _spy
        """
    )
    harness.makepyfile(
        """
        def test_pure_logic():
            assert 1 + 1 == 2
        """
    )
    result = harness.runpytest("-v")
    result.assert_outcomes(passed=1)
    marker = harness.path / "provisioned.marker"
    assert not marker.exists(), "nvda_reset must stay lazy: NVDA must never be provisioned"
