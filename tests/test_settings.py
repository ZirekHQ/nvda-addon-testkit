from pathlib import Path

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
