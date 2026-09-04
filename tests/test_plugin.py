from pathlib import Path

import pytest

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


def test_addon_bundle_requires_configuration(pytester):
    pytester.makepyfile(
        """
        def test_it(addon_bundle):
            pass
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*No add-on bundle configured*"])


def test_addon_bundle_requires_a_match(pytester):
    pytester.makepyprojecttoml(
        """
        [tool.nvda-testkit]
        addon-bundle = "dist/*.nvda-addon"
        """
    )
    pytester.makepyfile(
        """
        def test_it(addon_bundle):
            pass
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*No add-on bundle matched*Build it first*"])


def test_addon_bundle_refuses_more_than_one_match(pytester):
    pytester.makepyprojecttoml(
        """
        [tool.nvda-testkit]
        addon-bundle = "dist/*.nvda-addon"
        """
    )
    dist = pytester.path / "dist"
    dist.mkdir()
    (dist / "demo-1.0.0.nvda-addon").write_bytes(b"")
    (dist / "demo-1.0.1.nvda-addon").write_bytes(b"")
    pytester.makepyfile(
        """
        def test_it(addon_bundle):
            pass
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*matched 2 bundles*Clean the stale ones out*"])


def test_addon_bundle_returns_the_single_match(pytester):
    pytester.makepyprojecttoml(
        """
        [tool.nvda-testkit]
        addon-bundle = "dist/*.nvda-addon"
        """
    )
    dist = pytester.path / "dist"
    dist.mkdir()
    bundle = dist / "demo-1.0.0.nvda-addon"
    bundle.write_bytes(b"")
    pytester.makepyfile(
        """
        from pathlib import Path

        def test_it(addon_bundle):
            assert addon_bundle == Path("dist/demo-1.0.0.nvda-addon")
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_reset_failure_during_teardown_warns_instead_of_failing(harness):
    harness.makeconftest(
        """
        from nvda_testkit.client import NvdaClient

        _real_reset = NvdaClient.reset
        _calls = {"n": 0}

        def _reset(self):
            _calls["n"] += 1
            if _calls["n"] > 1:
                raise RuntimeError("synthetic reset failure")
            return _real_reset(self)

        NvdaClient.reset = _reset
        """
    )
    harness.makepyfile(
        """
        def test_it(nvda):
            pass
        """
    )
    result = harness.runpytest("-W", "default")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*reset() failed during teardown*synthetic reset failure*"])


def test_addon_under_test_installs_and_restarts_to_complete_it(harness):
    harness.makepyprojecttoml(
        """
        [tool.nvda-testkit]
        addon-bundle = "dist/*.nvda-addon"
        """
    )
    dist = harness.path / "dist"
    dist.mkdir()
    (dist / "demo-addon-1.0.0.nvda-addon").write_bytes(b"")
    harness.makepyfile(
        """
        from nvda_testkit.namespaces.addons import AddonState

        def test_it(addon_under_test, nvda_session):
            assert addon_under_test.name == "demo-addon-1.0.0.nvda-addon"
            assert nvda_session.addons.state("demo-addon") is AddonState.ENABLED
        """
    )
    harness.runpytest().assert_outcomes(passed=1)


def test_a_test_that_does_not_ask_for_nvda_never_starts_it(harness):
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
