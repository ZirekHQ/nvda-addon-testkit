import zipfile

from nvda_testkit.spybundle import spy_bundle_path


def test_the_built_bundle_is_a_valid_addon():
    bundle = spy_bundle_path()
    assert bundle.is_file(), "run `python tools/build_spy.py` first"
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        assert "manifest.ini" in names
        assert "globalPlugins/nvda_testkit_spy/__init__.py" in names
        assert "globalPlugins/nvda_testkit_spy/server.py" in names
        assert not any(name.endswith(".pyc") for name in names)
        assert not any("__pycache__" in name for name in names)
        manifest = archive.read("manifest.ini").decode("utf-8")
    assert "name = nvda-testkit-spy" in manifest
    assert "minimumNVDAVersion" in manifest
