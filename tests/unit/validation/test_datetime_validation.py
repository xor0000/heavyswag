from datetime import UTC, datetime, timedelta

import pytest

from heavyswag.errors import ValidationError
from heavyswag.validation import DateTimeField

_NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
_PAST = _NOW - timedelta(days=1)
_FUTURE = _NOW + timedelta(days=1)


def test_assembly_accepts_field_with_no_rules() -> None:
    DateTimeField().assembly()


def test_assembly_accepts_valid_bounds() -> None:
    DateTimeField(min=_PAST, max=_FUTURE).assembly()


def test_assembly_rejects_max_less_than_min() -> None:
    with pytest.raises(
        ValidationError, match="max must be greater than or equal to min"
    ):
        DateTimeField(min=_FUTURE, max=_PAST).assembly()


def test_assembly_rejects_is_past_and_is_future_conflict() -> None:
    with pytest.raises(
        ValidationError, match="is_past and is_future are mutually exclusive"
    ):
        DateTimeField(is_past=True, is_future=True).assembly()


def test_assembly_accepts_only_is_past() -> None:
    DateTimeField(is_past=True).assembly()


def test_assembly_accepts_only_is_future() -> None:
    DateTimeField(is_future=True).assembly()


# -- validate: checking an actual value against the rules --


def test_validate_accepts_any_value_when_no_rules_set() -> None:
    DateTimeField().validate(_NOW)


def test_validate_rejects_naive_value_when_require_tz() -> None:
    with pytest.raises(ValidationError, match="must be timezone-aware"):
        DateTimeField(require_tz=True).validate(_NOW.replace(tzinfo=None))


def test_validate_accepts_aware_value_when_require_tz() -> None:
    DateTimeField(require_tz=True).validate(_NOW.replace(tzinfo=UTC))


def test_validate_rejects_value_earlier_than_min() -> None:
    with pytest.raises(ValidationError, match="is earlier than"):
        DateTimeField(min=_NOW).validate(_PAST)


def test_validate_accepts_value_equal_to_min() -> None:
    DateTimeField(min=_NOW).validate(_NOW)


def test_validate_rejects_value_later_than_max() -> None:
    with pytest.raises(ValidationError, match="is later than"):
        DateTimeField(max=_NOW).validate(_FUTURE)


def test_validate_accepts_value_equal_to_max() -> None:
    DateTimeField(max=_NOW).validate(_NOW)


def test_validate_accepts_value_within_bounds() -> None:
    DateTimeField(min=_PAST, max=_FUTURE).validate(_NOW)


def test_validate_rejects_future_value_when_is_past() -> None:
    future = datetime.now() + timedelta(days=1)  # noqa: DTZ005
    with pytest.raises(ValidationError, match="must be in the past"):
        DateTimeField(is_past=True).validate(future)


def test_validate_accepts_past_value_when_is_past() -> None:
    past = datetime.now() - timedelta(days=1)  # noqa: DTZ005
    DateTimeField(is_past=True).validate(past)


def test_validate_rejects_past_value_when_is_future() -> None:
    past = datetime.now() - timedelta(days=1)  # noqa: DTZ005
    with pytest.raises(ValidationError, match="must be in the future"):
        DateTimeField(is_future=True).validate(past)


def test_validate_accepts_future_value_when_is_future() -> None:
    future = datetime.now() + timedelta(days=1)  # noqa: DTZ005
    DateTimeField(is_future=True).validate(future)


def test_validate_is_past_compares_aware_value_against_aware_now() -> None:
    past = datetime.now(UTC) - timedelta(days=1)
    DateTimeField(is_past=True).validate(past)


def test_validate_is_future_compares_aware_value_against_aware_now() -> None:
    future = datetime.now(UTC) + timedelta(days=1)
    DateTimeField(is_future=True).validate(future)
