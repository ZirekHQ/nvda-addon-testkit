from pathlib import Path

import pytest

from nvda_testkit.settings import TestkitSettings, load_settings

PYPROJECT = """
[tool.nvda-testkit]
nvda-channel = "alpha"
addon-bundle = "dist/demo-{version}.nvda-addon"
modules = ["audio"]
allow-eval = true
timeout-scale = 2.5
"""


def test_defaults_when_there_is_no_configuration(tmp_path):
    settings = load_settings(tmp_path / "pyproject.toml")
    assert settings == TestkitSettings()
    assert settings.channel == "stable"
    assert settings.modules == ()
    assert settings.allow_eval is False


def test_reads_the_tool_section(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text(PYPROJECT)
    settings = load_settings(path)
    assert settings.channel == "alpha"
    assert settings.addon_bundle == "dist/demo-{version}.nvda-addon"
    assert settings.modules == ("audio",)
    assert settings.allow_eval is True
    assert settings.timeout_scale == 2.5


def test_a_pyproject_without_our_section_falls_back_to_defaults(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\nname = "something"\n')
    assert load_settings(path) == TestkitSettings()


def test_overrides_beat_the_file(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text(PYPROJECT)
    settings = load_settings(path, {"channel": "stable", "timeout_scale": 1.0})
    assert settings.channel == "stable"
    assert settings.timeout_scale == 1.0
    assert settings.modules == ("audio",), "an unspecified override must not reset the file value"


def test_a_none_override_is_ignored_rather_than_clearing_the_file_value(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text(PYPROJECT)
    settings = load_settings(path, {"channel": None})
    assert settings.channel == "alpha"


def test_out_dir_is_a_path(tmp_path):
    settings = load_settings(tmp_path / "pyproject.toml", {"out_dir": "somewhere/else"})
    assert settings.out_dir == Path("somewhere/else")


def test_dsl_keys_are_read_from_pyproject(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.nvda-testkit]\n"
        "timeout = 20\n"
        "fail-on-log-errors = true\n"
        'ignore-log-errors = ["nvwave", "WASAPI"]\n'
    )
    settings = load_settings(pyproject)
    assert settings.timeout == 20.0
    assert settings.fail_on_log_errors is True
    assert settings.ignore_log_errors == ("nvwave", "WASAPI")


def test_dsl_settings_default_to_the_documented_values():
    settings = load_settings(Path("does-not-exist.toml"))
    assert settings.timeout == 10.0
    assert settings.fail_on_log_errors is False
    assert settings.ignore_log_errors == ()
    assert settings.verbose is False


def test_verbose_can_be_overridden():
    settings = load_settings(Path("does-not-exist.toml"), overrides={"verbose": True})
    assert settings.verbose is True


def test_a_bare_string_for_ignore_log_errors_is_one_pattern_not_characters(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.nvda-testkit]\nignore-log-errors = "nvwave"\n')
    assert load_settings(path).ignore_log_errors == ("nvwave",)


def test_a_list_for_ignore_log_errors_keeps_every_pattern(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.nvda-testkit]\nignore-log-errors = ["a", "b"]\n')
    assert load_settings(path).ignore_log_errors == ("a", "b")


def test_a_bare_string_for_modules_is_one_module(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.nvda-testkit]\nmodules = "audio"\n')
    assert load_settings(path).modules == ("audio",)


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf")])
def test_a_timeout_must_be_finite_and_positive(bad):
    with pytest.raises(ValueError, match="timeout must be a finite positive number"):
        load_settings(Path("does-not-exist.toml"), overrides={"timeout": bad})


def test_a_positive_timeout_is_accepted():
    assert load_settings(Path("does-not-exist.toml"), overrides={"timeout": 2}).timeout == 2.0


@pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf")])
def test_a_timeout_scale_must_be_finite_and_positive(bad):
    with pytest.raises(ValueError, match="timeout_scale must be a finite positive number"):
        load_settings(Path("does-not-exist.toml"), overrides={"timeout_scale": bad})


def test_a_positive_timeout_scale_is_accepted():
    settings = load_settings(Path("does-not-exist.toml"), overrides={"timeout_scale": 2.5})
    assert settings.timeout_scale == 2.5
