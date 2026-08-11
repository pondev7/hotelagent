"""PII discipline, as tests.

`CLAUDE.md`: never log message bodies, phone numbers in full, or payment
identifiers. Logs travel to aggregators, error trackers and screenshots — places
the database does not go and nobody audited.
"""

from hotelagent.logging import body_shape, redact_identifier


def test_a_phone_number_keeps_only_its_last_four_digits() -> None:
    assert redact_identifier("919812345678") == "********5678"


def test_a_short_identifier_is_fully_masked() -> None:
    """Keeping "the last four" of a four-digit value would reveal all of it."""
    assert redact_identifier("1234") == "****"
    assert redact_identifier("12") == "**"


def test_redaction_passes_through_empty_values() -> None:
    assert redact_identifier(None) is None
    assert redact_identifier("") == ""


def test_body_shape_describes_without_revealing() -> None:
    shape = body_shape("Is parking free at Sea Breeze?")

    assert shape == {"body_length": 30, "body_empty": False}
    assert "parking" not in str(shape)


def test_body_shape_handles_empty_and_missing_bodies() -> None:
    assert body_shape(None) == {"body_length": 0, "body_empty": True}
    assert body_shape("") == {"body_length": 0, "body_empty": True}
