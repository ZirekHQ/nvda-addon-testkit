from nvda_testkit.speechtypes import SpeechSequence, parse_sequence, parse_sequences


def _payload(items, cancelled=False, timestamp=123.0):
    return {"items": items, "timestamp": timestamp, "cancelled": cancelled}


def test_text_items_join_into_the_text_property():
    sequence = parse_sequence(
        _payload(
            [
                {"kind": "text", "text": "hello"},
                {"kind": "command", "type": "IndexCommand", "fields": {"index": 1}, "repr": "x"},
                {"kind": "text", "text": "world"},
            ]
        )
    )
    assert isinstance(sequence, SpeechSequence)
    assert sequence.text == "hello world"


def test_adjacent_text_items_with_no_intervening_command_join_with_one_space():
    sequence = parse_sequence(
        _payload([{"kind": "text", "text": "Install"}, {"kind": "text", "text": "button"}])
    )
    assert sequence.text == "Install button"


def test_a_text_item_that_is_an_explicit_space_does_not_double_up():
    sequence = parse_sequence(
        _payload(
            [
                {"kind": "text", "text": "Install"},
                {"kind": "text", "text": " "},
                {"kind": "text", "text": "button"},
            ]
        )
    )
    assert sequence.text == "Install button"


def test_commands_are_retrievable_by_type_name():
    sequence = parse_sequence(
        _payload(
            [
                {"kind": "command", "type": "IndexCommand", "fields": {"index": 1}, "repr": "a"},
                {"kind": "command", "type": "IndexCommand", "fields": {"index": 2}, "repr": "b"},
                {"kind": "command", "type": "BreakCommand", "fields": {"time": 50}, "repr": "c"},
            ]
        )
    )
    indexes = sequence.commands("IndexCommand")
    assert [item.fields["index"] for item in indexes] == [1, 2]
    assert len(sequence.commands("BreakCommand")) == 1
    assert sequence.commands("NoSuchCommand") == []


def test_matches_does_a_regex_search_over_the_text():
    sequence = parse_sequence(_payload([{"kind": "text", "text": "Dengjen Neural Voices"}]))
    assert sequence.matches("Neural")
    assert sequence.matches(r"^Dengjen")
    assert not sequence.matches("eSpeak")


def test_matching_is_case_insensitive_by_default():
    sequence = parse_sequence(_payload([{"kind": "text", "text": "Button"}]))
    assert sequence.matches("button")


def test_cancelled_and_timestamp_survive_parsing():
    sequence = parse_sequence(
        _payload([{"kind": "text", "text": "x"}], cancelled=True, timestamp=9.5)
    )
    assert sequence.cancelled is True
    assert sequence.timestamp == 9.5


def test_parse_sequences_maps_over_a_list():
    parsed = parse_sequences([_payload([{"kind": "text", "text": "a"}]) for _ in range(3)])
    assert len(parsed) == 3
    assert all(sequence.text == "a" for sequence in parsed)


def test_repr_shows_the_text_so_failures_are_readable():
    sequence = parse_sequence(_payload([{"kind": "text", "text": "press enter"}]))
    assert "press enter" in repr(sequence)
