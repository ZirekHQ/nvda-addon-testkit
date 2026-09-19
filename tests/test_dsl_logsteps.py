import pytest

from nvda_testkit.settings import load_settings


def _emit(nvda, level, message):
    nvda.rpc.call("log_emit", level, message)


def test_should_log_finds_a_record(make_dsl):
    nvda = make_dsl()
    _emit(nvda, "INFO", "testkit demo add-on loaded")
    nvda.should_log("add-on loaded", within=1)


def test_should_log_failure_lists_recent_records(make_dsl):
    nvda = make_dsl()
    _emit(nvda, "INFO", "starting")
    with pytest.raises(AssertionError) as failure:
        nvda.should_log("loaded", within=0.2)
    lines = str(failure.value).splitlines()
    assert lines[0] == 'Expected NVDA to log "loaded" within 0.2 seconds.'
    assert lines[2:4] == ["Logged so far, 1 item:", "1. INFO: starting"]


def test_no_errors_passes_on_a_clean_log(make_dsl):
    nvda = make_dsl()
    _emit(nvda, "INFO", "fine")
    nvda.should_have_no_errors()


def test_no_errors_fails_and_names_the_error(make_dsl):
    nvda = make_dsl()
    _emit(nvda, "ERROR", "boom")
    with pytest.raises(AssertionError, match="NVDA logged 1 unexpected error"):
        nvda.should_have_no_errors()


def test_ignored_errors_do_not_fail_and_are_listed_when_something_else_does(make_dsl):
    nvda = make_dsl(ignore_log_errors=("nvwave",))
    _emit(nvda, "ERROR", "nvwave could not open a device")
    nvda.should_have_no_errors()
    _emit(nvda, "ERROR", "boom")
    with pytest.raises(AssertionError, match="ignored by ignore-log-errors"):
        nvda.should_have_no_errors()


def test_a_per_call_ignore_pattern_is_honoured(make_dsl):
    nvda = make_dsl()
    _emit(nvda, "ERROR", "harmless noise")
    nvda.should_have_no_errors(ignoring=["harmless"])


def test_finish_does_nothing_when_fail_on_log_errors_is_off(make_dsl):
    nvda = make_dsl()
    _emit(nvda, "ERROR", "boom")
    nvda.finish()


def test_finish_fails_when_fail_on_log_errors_is_on(make_dsl):
    nvda = make_dsl(fail_on_log_errors=True)
    _emit(nvda, "ERROR", "boom")
    with pytest.raises(AssertionError, match="unexpected error"):
        nvda.finish()


def test_a_bare_string_setting_does_not_ignore_unrelated_errors(make_dsl, tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[tool.nvda-testkit]\nignore-log-errors = "nvwave"\n')
    nvda = make_dsl(ignore_log_errors=load_settings(path).ignore_log_errors)
    _emit(nvda, "ERROR", "unhandled exception in my add-on")
    with pytest.raises(AssertionError, match="NVDA logged 1 unexpected error"):
        nvda.should_have_no_errors()


def test_a_bare_string_ignoring_is_one_pattern_not_letters(make_dsl):
    nvda = make_dsl()
    _emit(nvda, "ERROR", "unhandled exception in my add-on")
    with pytest.raises(AssertionError, match="NVDA logged 1 unexpected error"):
        nvda.should_have_no_errors(ignoring="harmless")


def test_a_bare_string_ignoring_still_ignores_what_it_names(make_dsl):
    nvda = make_dsl()
    _emit(nvda, "ERROR", "harmless noise")
    nvda.should_have_no_errors(ignoring="harmless")


def test_unexpected_and_ignored_errors_keep_their_order(make_dsl):
    nvda = make_dsl(ignore_log_errors=("noise",))
    for message in ("boom one", "noise a", "boom two", "noise b"):
        _emit(nvda, "ERROR", message)
    with pytest.raises(AssertionError) as failure:
        nvda.should_have_no_errors()
    lines = str(failure.value).splitlines()
    assert lines[1:3] == ["1. ERROR: boom one", "2. ERROR: boom two"]
    assert lines[-2:] == ["1. ERROR: noise a", "2. ERROR: noise b"]
