import subprocess
import sys
import zipfile

import pytest

from nvda_testkit import portable
from nvda_testkit.errors import ProvisionError, TestkitError, UnsupportedPlatformError
from nvda_testkit.portable import (
    create_portable,
    extract_addon,
    render_nvda_ini,
    seed_user_config,
)


def test_rendered_ini_disables_everything_that_would_block_or_slow_a_test():
    text = render_nvda_ini()
    assert "[general]" in text
    assert "showWelcomeDialogAtStartup = False" in text
    assert "[update]" in text
    assert "autoCheck = False" in text
    assert "allowUsageStats = False" in text
    assert "[braille]" in text
    assert "display = noBraille" in text
    assert "schemaVersion" not in text


def test_rendered_ini_is_configobj_shaped_with_nested_sections():
    text = render_nvda_ini({"speech": {"synth": "espeak", "espeak": {"rate": 100}}})
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    assert "[speech]" in lines
    assert "synth = espeak" in lines
    assert "[[espeak]]" in lines
    assert "rate = 100" in lines


def test_overrides_merge_rather_than_replace():
    text = render_nvda_ini({"general": {"language": "en"}})
    assert "language = en" in text
    assert "showWelcomeDialogAtStartup = False" in text, "override must not drop defaults"


def test_seed_user_config_creates_the_expected_layout(tmp_path):
    user_config = seed_user_config(tmp_path)
    assert user_config == tmp_path / "userConfig"
    assert (user_config / "nvda.ini").is_file()
    assert (user_config / "addons").is_dir()


def _make_bundle(path, entries):
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return path


def test_extract_addon_unpacks_the_bundle(tmp_path):
    bundle = _make_bundle(
        tmp_path / "demo.nvda-addon",
        {"manifest.ini": "name = demo\n", "globalPlugins/demo.py": "# demo\n"},
    )
    dest = tmp_path / "out"
    extract_addon(bundle, dest)
    assert (dest / "manifest.ini").read_text() == "name = demo\n"
    assert (dest / "globalPlugins" / "demo.py").is_file()


def test_extract_addon_refuses_paths_that_escape_the_destination(tmp_path):
    bundle = _make_bundle(tmp_path / "evil.nvda-addon", {"../escaped.py": "pwned"})
    with pytest.raises(ProvisionError, match="escapes"):
        extract_addon(bundle, tmp_path / "out")
    assert not (tmp_path / "escaped.py").exists()


def test_extract_addon_rejects_a_bundle_without_a_manifest(tmp_path):
    bundle = _make_bundle(tmp_path / "nomanifest.nvda-addon", {"readme.txt": "hi"})
    with pytest.raises(ProvisionError, match=r"manifest\.ini"):
        extract_addon(bundle, tmp_path / "out")


def test_extract_addon_refuses_absolute_paths_that_escape(tmp_path):
    bundle = _make_bundle(
        tmp_path / "evil.nvda-addon",
        {"/etc/passwd": "pwned", "manifest.ini": "name=evil"},
    )
    with pytest.raises(ProvisionError, match="escapes"):
        extract_addon(bundle, tmp_path / "out")
    assert not (tmp_path / "etc" / "passwd").exists()


def test_create_portable_wraps_a_timeout_in_a_testkit_error(tmp_path, monkeypatch):
    launcher = tmp_path / "launcher.exe"
    launcher.write_bytes(b"stub")

    def explode(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd="launcher.exe", timeout=300, output="partial", stderr=None
        )

    monkeypatch.setattr(portable.sys, "platform", "win32")
    monkeypatch.setattr(portable.subprocess, "run", explode)

    with pytest.raises(ProvisionError, match="timed out"):
        portable.create_portable(launcher, tmp_path / "portable")
    with pytest.raises(TestkitError):
        portable.create_portable(launcher, tmp_path / "portable")


@pytest.mark.skipif(sys.platform == "win32", reason="checks the non-Windows guard")
def test_create_portable_refuses_to_pretend_on_non_windows(tmp_path):
    with pytest.raises(UnsupportedPlatformError, match="Windows"):
        create_portable(tmp_path / "launcher.exe", tmp_path / "portable")
