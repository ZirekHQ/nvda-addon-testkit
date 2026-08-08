import pytest


@pytest.fixture
def api(event_queue):
    import config
    from nvda_testkit_spy import config_api

    config.conf.clear()
    config.conf.update(
        {"speech": {"synth": "espeak", "espeak": {"rate": 50}}, "braille": {"display": "noBraille"}}
    )
    return config_api


def test_get_walks_a_path(api):
    assert api.config_get(["speech", "synth"]) == "espeak"
    assert api.config_get(["speech", "espeak", "rate"]) == 50


def test_get_a_missing_path_raises_with_the_path_in_the_message(api):
    with pytest.raises(KeyError, match=r"speech\.nosuch"):
        api.config_get(["speech", "nosuch"])


def test_set_writes_through(api):
    import config

    api.config_set(["speech", "synth"], "oneCore")
    assert config.conf["speech"]["synth"] == "oneCore"


def test_set_creates_intermediate_sections(api):
    import config

    api.config_set(["myAddon", "nested", "flag"], True)
    assert config.conf["myAddon"]["nested"]["flag"] is True


def test_snapshot_and_restore_round_trip(api):
    import config

    snapshot = api.config_snapshot()
    api.config_set(["speech", "synth"], "changed")
    api.config_set(["brand", "new"], 1)
    api.config_restore(snapshot)
    assert config.conf["speech"]["synth"] == "espeak"
    assert "brand" not in config.conf, "restore must drop keys added after the snapshot"


def test_a_snapshot_is_a_deep_copy_not_a_live_view(api):
    import config

    snapshot = api.config_snapshot()
    config.conf["speech"]["synth"] = "mutated after the snapshot"
    assert snapshot["speech"]["synth"] == "espeak"
