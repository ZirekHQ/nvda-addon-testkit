import pytest


@pytest.fixture
def tap():
    from nvda_testkit_spy import braille_tap

    braille_tap.install()
    braille_tap.braille_clear()
    yield braille_tap
    braille_tap.uninstall()


def _write(text):
    import braille.extensions as extensions

    extensions.pre_writeCells.notify(cells=[], rawText=text, currentCellCount=40)


def test_a_write_is_captured_as_raw_text(tap):
    assert tap.braille_index() == 0
    _write("Edit  multi line")
    assert tap.braille_index() == 1
    (entry,) = tap.braille_since(0)
    assert entry["text"] == "Edit  multi line"
    assert entry["timestamp"] > 0


def test_since_returns_only_later_writes(tap):
    _write("one")
    boundary = tap.braille_index()
    _write("two")
    assert [entry["text"] for entry in tap.braille_since(boundary)] == ["two"]


def test_clear_resets_the_index(tap):
    _write("noise")
    tap.braille_clear()
    assert tap.braille_index() == 0


def test_the_cell_count_is_forced_so_tests_do_not_depend_on_the_display(tap):
    import braille.extensions as extensions
    from braille.display import DisplayDimensions

    tap.braille_set_cell_count(80)
    dimensions = extensions.filter_displayDimensions.apply(DisplayDimensions(2, 20))
    assert dimensions.numCols == 80
    assert dimensions.numRows == 1
    assert tap.braille_cell_count() == 80


def test_an_empty_write_is_still_recorded(tap):
    _write("")
    assert tap.braille_index() == 1, "a blank display is a real event, not a non-event"


def test_uninstall_unregisters_the_handler(tap):
    tap.uninstall()
    tap.install()
    tap.braille_clear()
    _write("once")
    assert tap.braille_index() == 1
