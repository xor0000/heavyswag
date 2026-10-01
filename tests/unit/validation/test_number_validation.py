import pytest

from heavyswag.errors import ValidationError
from heavyswag.validation import NumField


def test_assembly_accepts_field_with_no_rules() -> None:
    NumField[int]().assembly()


def test_assembly_accepts_valid_bounds() -> None:
    NumField[int](min=1, max=5).assembly()


def test_assembly_rejects_max_less_than_min() -> None:
    with pytest.raises(
        ValidationError, match="max must be greater than or equal to min"
    ):
        NumField[int](min=5, max=1).assembly()


def test_assembly_rejects_is_even_and_is_odd_conflict() -> None:
    with pytest.raises(
        ValidationError, match="is_even and is_odd are mutually exclusive"
    ):
        NumField[int](is_even=True, is_odd=True).assembly()


def test_assembly_accepts_only_is_even() -> None:
    NumField[int](is_even=True).assembly()


def test_assembly_accepts_only_is_odd() -> None:
    NumField[int](is_odd=True).assembly()


def test_validate_accepts_any_value_when_no_rules_set() -> None:
    NumField[int]().validate(0)


def test_validate_rejects_value_below_min() -> None:
    with pytest.raises(ValidationError, match="Value is less than 5"):
        NumField[int](min=5).validate(4)


def test_validate_accepts_value_equal_to_min() -> None:
    NumField[int](min=5).validate(5)


def test_validate_rejects_value_above_max() -> None:
    with pytest.raises(ValidationError, match="Value is greater than 5"):
        NumField[int](max=5).validate(6)


def test_validate_accepts_value_equal_to_max() -> None:
    NumField[int](max=5).validate(5)


def test_validate_accepts_value_within_bounds() -> None:
    NumField[int](min=1, max=10).validate(5)


def test_validate_rejects_odd_value_when_is_even() -> None:
    with pytest.raises(ValidationError, match="Value must be even"):
        NumField[int](is_even=True).validate(3)


def test_validate_accepts_even_value_when_is_even() -> None:
    NumField[int](is_even=True).validate(4)


def test_validate_rejects_even_value_when_is_odd() -> None:
    with pytest.raises(ValidationError, match="Value must be odd"):
        NumField[int](is_odd=True).validate(4)


def test_validate_accepts_odd_value_when_is_odd() -> None:
    NumField[int](is_odd=True).validate(3)


def test_validate_works_with_float_bounds() -> None:
    NumField[float](min=0.5, max=10.5).validate(5.5)


def test_validate_rejects_float_value_below_min() -> None:
    with pytest.raises(ValidationError, match=r"Value is less than 0\.5"):
        NumField[float](min=0.5).validate(0.1)


def test_validate_accepts_whole_float_when_is_even() -> None:
    NumField[float](is_even=True).validate(4.0)


def test_validate_rejects_fractional_float_when_is_even() -> None:
    with pytest.raises(ValidationError, match="Value must be even"):
        NumField[float](is_even=True).validate(3.5)
