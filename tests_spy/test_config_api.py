import xmlrpc.client

import pytest

from tests_spy import nvda_stubs


@pytest.fixture
def api(event_queue):
    import config
    from nvda_testkit_spy import config_api

    # Rebuilt rather than cleared: a real config.conf has no clear() or update().
    config.conf = nvda_stubs.FakeConfigManager(nvda_stubs.DEFAULT_CONFIG)
    return config_api


def test_get_walks_a_path(api):
    assert api.config_get(["speech", "synth"]) == "espeak"
    assert api.config_get(["speech", "espeak", "rate"]) == 50


def test_get_a_missing_path_raises_with_the_path_in_the_message(api):
    with pytest.raises(KeyError, match=r"speech\.nosuch"):
        api.config_get(["speech", "nosuch"])


def test_get_of_a_section_returns_something_xmlrpc_can_carry(api):
    section = api.config_get(["speech"])
    assert section == {"synth": "espeak", "espeak": {"rate": 50}}
    xmlrpc.client.dumps((section,), allow_none=True)


def test_get_of_the_whole_config_returns_something_xmlrpc_can_carry(api):
    whole = api.config_get([])
    assert whole["braille"]["display"] == "noBraille"
    xmlrpc.client.dumps((whole,), allow_none=True)


def test_set_writes_through(api):
    import config

    api.config_set(["speech", "synth"], "oneCore")
    assert config.conf["speech"]["synth"] == "oneCore"


def test_set_creates_intermediate_sections(api):
    import config

    api.config_set(["myAddon", "nested", "flag"], True)
    assert config.conf["myAddon"]["nested"]["flag"] is True


def test_set_of_a_leaf_does_not_wipe_the_section_it_walks_through(api):
    import config

    api.config_set(["speech", "espeak", "rate"], 60)
    assert config.conf["speech"]["espeak"]["rate"] == 60
    assert config.conf["speech"]["synth"] == "espeak", "walking past a section must not empty it"


def test_snapshot_is_a_plain_dict_xmlrpc_can_carry(api):
    snapshot = api.config_snapshot()
    assert type(snapshot) is dict
    assert type(snapshot["speech"]) is dict
    xmlrpc.client.dumps((snapshot,), allow_none=True)


def test_snapshot_and_restore_round_trip(api):
    import config

    snapshot = api.config_snapshot()
    api.config_set(["speech", "synth"], "changed")
    api.config_set(["brand", "new"], 1)
    api.config_restore(snapshot)
    assert config.conf["speech"]["synth"] == "espeak"
    # The key itself survives: ConfigManager exposes no way to delete one. What
    # restore can guarantee, and does, is that nothing is left inside it.
    assert config.conf["brand"].dict() == {}


def test_a_snapshot_is_a_deep_copy_not_a_live_view(api):
    import config

    snapshot = api.config_snapshot()
    config.conf["speech"]["synth"] = "mutated after the snapshot"
    assert snapshot["speech"]["synth"] == "espeak"


def test_restore_runs_twice_without_error(api):
    """reset() calls it before and after every test; the second must work too."""
    snapshot = api.config_snapshot()
    api.config_restore(snapshot)
    api.config_restore(snapshot)


def test_snapshot_stringifies_a_leaf_xmlrpc_cannot_marshal(api):
    """Real NVDA's config tree holds leaves .dict() alone does not flatten --

    e.g. a config.featureFlag entry comes back as a raw, unresolved
    `property` descriptor rather than its value.
    """
    import config

    config.conf["quirky"] = {"flag": property(lambda self: True)}
    snapshot = api.config_snapshot()
    assert isinstance(snapshot["quirky"]["flag"], str)
    xmlrpc.client.dumps((snapshot,), allow_none=True)
