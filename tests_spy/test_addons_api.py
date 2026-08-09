import pytest


@pytest.fixture
def api(event_queue):
    import addonHandler
    from nvda_testkit_spy import addons_api

    addonHandler.INSTALLED.clear()
    addonHandler.NEXT_INSTALL_OUTCOME = "ok"
    return addons_api


def test_an_unknown_addon_reports_not_installed(api):
    assert api.addons_state("nothing-here") == "NOT_INSTALLED"


def test_install_leaves_the_addon_pending_not_enabled(api):
    result = api.addons_install("/tmp/demo.nvda-addon")
    assert result["name"] == "demo-addon"
    assert result["state"] == "PENDING_INSTALL"
    assert api.addons_state("demo-addon") == "PENDING_INSTALL"


def test_list_reports_name_version_and_state(api):
    api.addons_install("/tmp/demo.nvda-addon")
    (entry,) = api.addons_list()
    assert entry["name"] == "demo-addon"
    assert entry["version"] == "1.0.0"
    assert entry["state"] == "PENDING_INSTALL"


def test_an_addon_that_finished_installing_reports_enabled(api):
    import addonHandler

    api.addons_install("/tmp/demo.nvda-addon")
    addon = addonHandler.INSTALLED[0]
    addon.isPendingInstall = False
    addon.isRunning = True
    assert api.addons_state("demo-addon") == "ENABLED"


def test_a_disabled_addon_reports_disabled(api):
    import addonHandler

    api.addons_install("/tmp/demo.nvda-addon")
    addon = addonHandler.INSTALLED[0]
    addon.isPendingInstall = False
    addon.isDisabled = True
    assert api.addons_state("demo-addon") == "DISABLED"


def test_remove_marks_pending_remove(api):
    import addonHandler

    api.addons_install("/tmp/demo.nvda-addon")
    addonHandler.INSTALLED[0].isPendingInstall = False
    api.addons_remove("demo-addon")
    assert api.addons_state("demo-addon") == "PENDING_REMOVE"


def test_removing_something_absent_is_an_error_not_a_silent_no_op(api):
    with pytest.raises(LookupError, match="not installed"):
        api.addons_remove("never-existed")


def test_a_bundle_that_will_not_extract_reports_why(api):
    import addonHandler

    addonHandler.NEXT_INSTALL_OUTCOME = "extract-failure"
    with pytest.raises(RuntimeError, match="could not extract"):
        api.addons_install("/tmp/corrupt.nvda-addon")


def test_a_failing_on_install_task_is_not_reported_as_success(api):
    import addonHandler

    addonHandler.NEXT_INSTALL_OUTCOME = "install-task-failure"
    with pytest.raises(RuntimeError, match="onInstall failed"):
        api.addons_install("/tmp/demo.nvda-addon")
    assert api.addons_state("demo-addon") == "NOT_INSTALLED"


def test_a_failed_install_names_the_underlying_exception(api):
    import addonHandler

    addonHandler.NEXT_INSTALL_OUTCOME = "install-task-failure"
    with pytest.raises(RuntimeError, match="RuntimeError: onInstall exploded"):
        api.addons_install("/tmp/demo.nvda-addon")
