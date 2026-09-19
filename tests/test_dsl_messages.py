from nvda_testkit.actionmark import START, ActionMark
from nvda_testkit.dsl import messages

PRESS = ActionMark(3, "pressing NVDA+t")


def _expected(heard, mark=PRESS, verbose=False, hint=messages.PLAIN_HINT):
    return messages.expected_to_hear(
        '"PM"', within=10, elapsed=10.05, mark=mark, heard=heard, verbose=verbose, hint=hint
    )


def test_expected_to_hear_lists_what_was_heard_in_order():
    assert _expected(["12 colon 00", "Tuesday"]).splitlines() == [
        'Expected to hear "PM" within 10 seconds after pressing NVDA+t.',
        "Time elapsed: 10.05 seconds.",
        "Heard since that action, 2 items:",
        '1. "12 colon 00"',
        '2. "Tuesday"',
        "Nothing matched. Matching is case-insensitive plain text; use matching= for a regex.",
    ]


def test_expected_to_hear_says_so_when_nothing_was_heard():
    lines = _expected([]).splitlines()
    assert lines[2] == "Heard nothing since that action."
    assert len(lines) == 3


def test_before_any_action_the_message_refers_to_the_start_of_the_test():
    lines = _expected(["x"], mark=START).splitlines()
    assert lines[0].endswith("within 10 seconds from the start of the test.")
    assert lines[2] == "Heard since the start of the test, 1 item:"


def test_one_second_is_singular():
    assert messages.seconds(1) == "1 second"
    assert messages.seconds(0.5) == "0.5 seconds"


def test_long_lists_are_truncated_with_the_count_stated():
    lines = _expected([f"item {n}" for n in range(12)]).splitlines()
    assert lines[-2] == "2 more items not shown; run with --nvda-verbose to see all"
    assert len(lines) <= 15


def test_verbose_shows_everything():
    lines = _expected([f"item {n}" for n in range(12)], verbose=True).splitlines()
    assert lines[3:6] == [
        '1. "item 0"',
        '2. "item 1"',
        '3. "item 2"',
    ]
    assert '12. "item 11"' in lines
    assert "more items not shown" not in "\n".join(lines)


def test_unexpected_hearing_lists_the_offending_speech():
    text = messages.unexpected_hearing(
        '"error"', for_seconds=1, mark=PRESS, heard=["an error occurred"], verbose=False
    )
    assert text.splitlines() == [
        'Expected not to hear "error" for 1 second after pressing NVDA+t, but heard:',
        '1. "an error occurred"',
    ]


def test_expected_log_lists_recent_records():
    text = messages.expected_log(
        '"loaded"',
        within=10,
        elapsed=10.0,
        records=["INFO: starting"],
        verbose=False,
        hint=messages.PLAIN_HINT,
    )
    assert text.splitlines()[:4] == [
        'Expected NVDA to log "loaded" within 10 seconds.',
        "Time elapsed: 10.00 seconds.",
        "Logged so far, 1 item:",
        "1. INFO: starting",
    ]


def test_expected_log_says_so_when_nothing_was_logged():
    text = messages.expected_log(
        '"x"', within=1, elapsed=1.0, records=[], verbose=False, hint=messages.PLAIN_HINT
    )
    assert text.splitlines()[2] == "Nothing was logged."


def test_no_errors_failure_separates_ignored_records():
    text = messages.no_errors_failure(["ERROR: boom"], ["ERROR: nvwave"], verbose=False)
    assert text.splitlines() == [
        "NVDA logged 1 unexpected error:",
        "1. ERROR: boom",
        "Also logged, and ignored by ignore-log-errors, 1 item:",
        "1. ERROR: nvwave",
    ]


def test_truncation_singular_with_one_more_item():
    lines = _expected([f"item {n}" for n in range(11)]).splitlines()
    assert lines[-2] == "1 more item not shown; run with --nvda-verbose to see all"


def test_plural_error_count():
    text = messages.no_errors_failure(["ERROR: boom", "ERROR: crash"], [], verbose=False)
    assert text.splitlines()[0] == "NVDA logged 2 unexpected errors:"


def test_regex_hint_in_expected_to_hear():
    lines = _expected(["x"], hint=messages.REGEX_HINT).splitlines()
    assert (
        "Nothing matched. The pattern is a regular expression, searched case-insensitively."
    ) in lines[-1]


def test_newlines_collapsed_in_quoted_items():
    text = messages.expected_to_hear(
        '"x"',
        within=1,
        elapsed=1.0,
        mark=PRESS,
        heard=["a\nb"],
        verbose=False,
        hint=messages.PLAIN_HINT,
    )
    assert '1. "a b"' in text.splitlines()


def test_newlines_collapsed_in_log_records():
    text = messages.expected_log(
        '"x"',
        within=1,
        elapsed=1.0,
        records=["ERROR: a\nstack\ntrace"],
        verbose=False,
        hint=messages.PLAIN_HINT,
    )
    assert "1. ERROR: a stack trace" in text.splitlines()


def test_no_errors_failure_with_many_records_stays_under_15_lines():
    unexpected = [f"ERROR: unexpected_{n}" for n in range(20)]
    ignored = [f"ERROR: ignored_{n}" for n in range(20)]
    text = messages.no_errors_failure(unexpected, ignored, verbose=False)
    lines = text.splitlines()
    assert len(lines) <= 15
    assert "14 more items not shown" in text
    assert "17 more items not shown" in text


def test_no_errors_failure_verbose_shows_all_records():
    unexpected = [f"ERROR: unexpected_{n}" for n in range(20)]
    ignored = [f"ERROR: ignored_{n}" for n in range(20)]
    text = messages.no_errors_failure(unexpected, ignored, verbose=True)
    assert "20. ERROR: unexpected_19" in text
    assert "20. ERROR: ignored_19" in text
