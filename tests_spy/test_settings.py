from nvda_testkit_spy.settings import OUTDIR_VARIABLE, TOKEN_VARIABLE, Settings


def test_both_variables_yield_settings():
    settings = Settings.from_environ({TOKEN_VARIABLE: "tok", OUTDIR_VARIABLE: "/out"})
    assert settings == Settings(token="tok", out_dir="/out")


def test_a_missing_token_yields_none():
    assert Settings.from_environ({OUTDIR_VARIABLE: "/out"}) is None


def test_a_missing_out_dir_yields_none():
    assert Settings.from_environ({TOKEN_VARIABLE: "tok"}) is None


def test_empty_values_count_as_missing():
    assert Settings.from_environ({TOKEN_VARIABLE: "", OUTDIR_VARIABLE: "/out"}) is None


def test_it_reads_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv(TOKEN_VARIABLE, "tok")
    monkeypatch.setenv(OUTDIR_VARIABLE, "/out")
    assert Settings.from_environ() == Settings(token="tok", out_dir="/out")
