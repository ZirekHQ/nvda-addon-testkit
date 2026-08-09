# coding: utf-8
"""Convert NVDA speech sequences into something XML-RPC can carry.

A speech sequence is a list of strings and SpeechCommand instances. Commands
are ordinary Python objects with no marshalling support, so each one becomes a
dict of its public attributes plus its repr. The repr is the fallback the host
falls back on when a field could not be represented.
"""

_SCALARS = (str, int, float, bool, type(None))


def _scalarise(value):
    if isinstance(value, _SCALARS):
        return value
    return repr(value)


def serialise_command(command):
    fields = {}
    try:
        attributes = vars(command)
    except TypeError:
        # A __slots__-only command has no __dict__. Core NVDA commands all have
        # one, but a third-party synth's might not -- fall back to the repr
        # rather than losing the whole sequence.
        attributes = {}
    for name, value in attributes.items():
        if name.startswith("_"):
            continue
        fields[name] = _scalarise(value)
    return {
        "kind": "command",
        "type": type(command).__name__,
        "fields": fields,
        "repr": repr(command),
    }


def serialise_sequence(sequence):
    items = []
    for element in sequence:
        if isinstance(element, str):
            items.append({"kind": "text", "text": element})
        else:
            items.append(serialise_command(element))
    return items
