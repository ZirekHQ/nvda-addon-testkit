def test_plain_strings_become_text_items():
    from nvda_testkit_spy.serialise import serialise_sequence

    items = serialise_sequence(["hello", "world"])
    assert items == [
        {"kind": "text", "text": "hello"},
        {"kind": "text", "text": "world"},
    ]


def test_commands_become_typed_items_with_their_public_fields():
    from nvda_testkit_spy.serialise import serialise_sequence
    from speech.commands import IndexCommand

    (item,) = serialise_sequence([IndexCommand(7)])
    assert item["kind"] == "command"
    assert item["type"] == "IndexCommand"
    assert item["fields"]["index"] == 7
    assert "IndexCommand" in item["repr"]


def test_unmarshallable_field_values_are_stringified_not_dropped():
    from nvda_testkit_spy.serialise import serialise_sequence

    class Weird:
        def __init__(self):
            self.payload = object()

        def __repr__(self):
            return "<Weird>"

    (item,) = serialise_sequence([Weird()])
    assert item["type"] == "Weird"
    assert isinstance(item["fields"]["payload"], str)
    assert item["repr"] == "<Weird>"


def test_private_attributes_are_not_serialised():
    from nvda_testkit_spy.serialise import serialise_sequence

    class Command:
        def __init__(self):
            self.visible = 1
            self._hidden = 2

    (item,) = serialise_sequence([Command()])
    assert "visible" in item["fields"]
    assert "_hidden" not in item["fields"]


def test_a_slots_only_command_degrades_to_an_empty_fields_dict_not_a_crash():
    from nvda_testkit_spy.serialise import serialise_sequence

    class SlottedCommand:
        __slots__ = ("value",)

        def __init__(self, value):
            self.value = value

        def __repr__(self):
            return f"SlottedCommand({self.value!r})"

    (item,) = serialise_sequence([SlottedCommand(5)])
    assert item == {
        "kind": "command",
        "type": "SlottedCommand",
        "fields": {},
        "repr": "SlottedCommand(5)",
    }


def test_everything_produced_survives_an_xmlrpc_round_trip():
    import xmlrpc.client

    from nvda_testkit_spy.serialise import serialise_sequence
    from speech.commands import BreakCommand, IndexCommand, LangChangeCommand

    items = serialise_sequence(
        ["text", IndexCommand(1), LangChangeCommand("en_GB"), BreakCommand(500)]
    )
    payload = xmlrpc.client.dumps((items,), allow_none=True)
    ((restored,), _) = xmlrpc.client.loads(payload)
    assert restored == items
