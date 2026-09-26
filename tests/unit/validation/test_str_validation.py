import pytest

from heavyswag.errors import ValidationError
from heavyswag.validation import StrField

# -- assembly: rule self-consistency, no value involved --


def test_assembly_accepts_field_with_no_rules() -> None:
    StrField().assembly()


def test_assembly_accepts_valid_length_bounds() -> None:
    StrField(min_len=1, max_len=5).assembly()


def test_assembly_rejects_negative_min_len() -> None:
    with pytest.raises(ValidationError, match="min_len must not be negative"):
        StrField(min_len=-1).assembly()


def test_assembly_rejects_negative_max_len() -> None:
    with pytest.raises(ValidationError, match="max_len must not be negative"):
        StrField(max_len=-1).assembly()


def test_assembly_rejects_max_len_less_than_min_len() -> None:
    with pytest.raises(
        ValidationError, match="max_len must be greater than or equal"
    ):
        StrField(min_len=5, max_len=2).assembly()


def test_assembly_rejects_unknown_pattern_preset() -> None:
    with pytest.raises(ValidationError, match="Unknown pattern_preset"):
        StrField(pattern_preset="not-a-real-preset").assembly()  # type: ignore[arg-type]


def test_assembly_rejects_pattern_preset_combined_with_other_fields() -> None:
    with pytest.raises(
        ValidationError, match="must be set without any other StrField"
    ):
        StrField(pattern_preset="email", min_len=5).assembly()


@pytest.mark.parametrize(
    "preset",
    ["email", "url", "credit_card", "phone", "slug", "password"],
)
def test_assembly_accepts_pattern_preset_alone(preset: str) -> None:
    StrField(pattern_preset=preset).assembly()  # type: ignore[arg-type]


def test_assembly_accepts_valid_pattern() -> None:
    StrField(pattern=r"^[a-z]+$").assembly()


def test_assembly_rejects_invalid_pattern_regex() -> None:
    with pytest.raises(ValidationError, match="Invalid pattern"):
        StrField(pattern="(unbalanced").assembly()


def test_assembly_rejects_first_is_upper_and_lover_conflict() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        StrField(first_is_upper=True, first_is_lover=True).assembly()


def test_assembly_rejects_is_upper_and_is_lower_conflict() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        StrField(is_upper=True, is_lower=True).assembly()


def test_assembly_rejects_is_upper_with_has_lowercase_conflict() -> None:
    with pytest.raises(
        ValidationError, match="incompatible with has_lowercase=True"
    ):
        StrField(is_upper=True, has_lowercase=True).assembly()


def test_assembly_rejects_is_lower_with_has_uppercase_conflict() -> None:
    with pytest.raises(
        ValidationError, match="incompatible with has_uppercase=True"
    ):
        StrField(is_lower=True, has_uppercase=True).assembly()


def test_assembly_rejects_negative_min_special_symbols() -> None:
    with pytest.raises(
        ValidationError, match="min_special_symbols must not be negative"
    ):
        StrField(min_special_symbols=-1).assembly()


def test_assembly_rejects_has_special_symbols_false_with_min_special_symbols() -> (
    None
):
    with pytest.raises(
        ValidationError,
        match="has_special_symbols=False is incompatible",
    ):
        StrField(has_special_symbols=False, min_special_symbols=1).assembly()


def test_assembly_rejects_is_alpha_with_has_digits() -> None:
    with pytest.raises(
        ValidationError, match="incompatible with has_digits=True"
    ):
        StrField(is_alpha=True, has_digits=True).assembly()


def test_assembly_rejects_is_alpha_with_has_special_symbols() -> None:
    with pytest.raises(
        ValidationError, match="incompatible with has_special_symbols=True"
    ):
        StrField(is_alpha=True, has_special_symbols=True).assembly()


def test_assembly_rejects_no_consecutive_repeats_below_minimum() -> None:
    with pytest.raises(
        ValidationError, match="no_consecutive_repeats must be at least 2"
    ):
        StrField(no_consecutive_repeats=1).assembly()


def test_assembly_accepts_no_consecutive_repeats_at_minimum() -> None:
    StrField(no_consecutive_repeats=2).assembly()


def test_assembly_rejects_char_list_with_non_bool_first_element() -> None:
    with pytest.raises(ValidationError, match="char_list\\[0\\] must be a bool"):
        StrField(char_list=("yes", "abc")).assembly()  # type: ignore[arg-type]


def test_assembly_rejects_char_list_with_empty_charset() -> None:
    with pytest.raises(
        ValidationError, match="must not contain an empty character set"
    ):
        StrField(char_list=(True, "")).assembly()


def test_assembly_accepts_valid_char_list() -> None:
    StrField(char_list=(True, "qwerty")).assembly()


# -- validate: checking an actual value against the rules --


def test_validate_accepts_any_value_when_no_rules_set() -> None:
    StrField().validate("anything at all")


def test_validate_rejects_value_shorter_than_min_len() -> None:
    with pytest.raises(ValidationError, match="length is less than"):
        StrField(min_len=5).validate("ab")


def test_validate_rejects_value_longer_than_max_len() -> None:
    with pytest.raises(ValidationError, match="length is greater than"):
        StrField(max_len=2).validate("abc")


def test_validate_accepts_value_within_length_bounds() -> None:
    StrField(min_len=1, max_len=5).validate("abc")


def test_validate_rejects_value_not_matching_pattern() -> None:
    with pytest.raises(ValidationError, match="does not match pattern"):
        StrField(pattern=r"^[a-z]+$").validate("ABC")


def test_validate_accepts_value_matching_pattern() -> None:
    StrField(pattern=r"^[a-z]+$").validate("abc")


@pytest.mark.parametrize(
    ("preset", "value"),
    [
        ("email", "user@example.com"),
        ("url", "https://example.com/path"),
        ("credit_card", "4111111111111111"),
        ("phone", "+15551234567"),
        ("slug", "my-blog-post"),
        ("password", "Passw0rd"),
    ],
)
def test_validate_accepts_value_matching_pattern_preset(
    preset: str, value: str
) -> None:
    StrField(pattern_preset=preset).validate(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("preset", "value"),
    [
        ("email", "not-an-email"),
        ("url", "not a url"),
        ("credit_card", "abc"),
        ("phone", "not-a-phone"),
        ("slug", "Not A Slug"),
        ("password", "short"),
    ],
)
def test_validate_rejects_value_not_matching_pattern_preset(
    preset: str, value: str
) -> None:
    with pytest.raises(ValidationError, match="does not match pattern"):
        StrField(pattern_preset=preset).validate(value)  # type: ignore[arg-type]


def test_validate_rejects_first_is_upper_with_lowercase_first_char() -> None:
    with pytest.raises(ValidationError, match="First character must be uppercase"):
        StrField(first_is_upper=True).validate("david")


def test_validate_rejects_first_is_upper_with_empty_value() -> None:
    with pytest.raises(ValidationError, match="First character must be uppercase"):
        StrField(first_is_upper=True).validate("")


def test_validate_accepts_first_is_upper_with_uppercase_first_char() -> None:
    StrField(first_is_upper=True).validate("David")


def test_validate_rejects_first_is_lover_with_uppercase_first_char() -> None:
    with pytest.raises(ValidationError, match="First character must be lowercase"):
        StrField(first_is_lover=True).validate("David")


def test_validate_accepts_first_is_lover_with_lowercase_first_char() -> None:
    StrField(first_is_lover=True).validate("david")


def test_validate_rejects_is_upper_when_not_fully_upper() -> None:
    with pytest.raises(ValidationError, match="must be uppercase"):
        StrField(is_upper=True).validate("Rub")


def test_validate_accepts_is_upper_when_fully_upper() -> None:
    StrField(is_upper=True).validate("RUB")


def test_validate_rejects_is_lower_when_not_fully_lower() -> None:
    with pytest.raises(ValidationError, match="must be lowercase"):
        StrField(is_lower=True).validate("Rub")


def test_validate_accepts_is_lower_when_fully_lower() -> None:
    StrField(is_lower=True).validate("rub")


def test_validate_rejects_has_uppercase_missing() -> None:
    with pytest.raises(
        ValidationError, match="must contain an uppercase character"
    ):
        StrField(has_uppercase=True).validate("password1")


def test_validate_accepts_has_uppercase_present() -> None:
    StrField(has_uppercase=True).validate("Password1")


def test_validate_rejects_has_lowercase_missing() -> None:
    with pytest.raises(
        ValidationError, match="must contain a lowercase character"
    ):
        StrField(has_lowercase=True).validate("PASSWORD1")


def test_validate_accepts_has_lowercase_present() -> None:
    StrField(has_lowercase=True).validate("Password1")


def test_validate_rejects_has_digits_true_missing_digit() -> None:
    with pytest.raises(ValidationError, match="must contain digits"):
        StrField(has_digits=True).validate("UserNickname")


def test_validate_accepts_has_digits_true_with_digit() -> None:
    StrField(has_digits=True).validate("UserNickname17")


def test_validate_rejects_has_digits_false_with_digit() -> None:
    with pytest.raises(ValidationError, match="must not contain digits"):
        StrField(has_digits=False).validate("UserNickname17")


def test_validate_accepts_has_digits_false_without_digit() -> None:
    StrField(has_digits=False).validate("UserNickname")


def test_validate_rejects_has_special_symbols_true_missing() -> None:
    with pytest.raises(ValidationError, match="must contain special symbols"):
        StrField(has_special_symbols=True).validate("Passw0rd")


def test_validate_accepts_has_special_symbols_true_present() -> None:
    StrField(has_special_symbols=True).validate("Passw0rd!")


def test_validate_rejects_has_special_symbols_false_with_symbol() -> None:
    with pytest.raises(
        ValidationError, match="must not contain special symbols"
    ):
        StrField(has_special_symbols=False).validate("Passw0rd!")


def test_validate_accepts_has_special_symbols_false_without_symbol() -> None:
    StrField(has_special_symbols=False).validate("Passw0rd")


def test_validate_rejects_min_special_symbols_not_met() -> None:
    with pytest.raises(
        ValidationError, match="must contain at least 2 special symbols"
    ):
        StrField(min_special_symbols=2).validate("Passw0rd!")


def test_validate_accepts_min_special_symbols_met() -> None:
    StrField(min_special_symbols=2).validate("Passw0rd!!")


def test_validate_rejects_has_whitespace_true_missing() -> None:
    with pytest.raises(
        ValidationError, match="must contain whitespace characters"
    ):
        StrField(has_whitespace=True).validate("JohnDoe")


def test_validate_accepts_has_whitespace_true_present() -> None:
    StrField(has_whitespace=True).validate("John Doe")


def test_validate_rejects_has_whitespace_false_with_whitespace() -> None:
    with pytest.raises(
        ValidationError, match="must not contain whitespace characters"
    ):
        StrField(has_whitespace=False).validate("John Doe")


def test_validate_accepts_has_whitespace_false_without_whitespace() -> None:
    StrField(has_whitespace=False).validate("JohnDoe")


def test_validate_rejects_leading_trailing_whitespace() -> None:
    with pytest.raises(
        ValidationError, match="must not have leading/trailing whitespace"
    ):
        StrField(no_leading_trailing_whitespace=True).validate(" John")


def test_validate_accepts_value_without_leading_trailing_whitespace() -> None:
    StrField(no_leading_trailing_whitespace=True).validate("John")


def test_validate_strips_whitespace_before_other_checks() -> None:
    StrField(max_len=2, strip_whitespace=True).validate("  ab  ")


def test_validate_without_strip_whitespace_counts_raw_length() -> None:
    with pytest.raises(ValidationError, match="length is greater than"):
        StrField(max_len=2).validate("  ab  ")


def test_validate_rejects_consecutive_repeats() -> None:
    with pytest.raises(
        ValidationError, match="must not contain 2 identical characters"
    ):
        StrField(no_consecutive_repeats=2).validate("aab")


def test_validate_accepts_value_below_repeat_threshold() -> None:
    StrField(no_consecutive_repeats=3).validate("aab")


def test_validate_skips_repeat_check_when_unset() -> None:
    StrField().validate("aaaaaa")


def test_validate_rejects_is_alpha_with_non_letter() -> None:
    with pytest.raises(ValidationError, match="must consist of letters only"):
        StrField(is_alpha=True).validate("John1")


def test_validate_accepts_is_alpha_with_letters_only() -> None:
    StrField(is_alpha=True).validate("John")


def test_validate_rejects_is_alnum_with_symbol() -> None:
    with pytest.raises(
        ValidationError, match="must consist of letters and digits only"
    ):
        StrField(is_alnum=True).validate("John!")


def test_validate_accepts_is_alnum_with_letters_and_digits() -> None:
    StrField(is_alnum=True).validate("John1")


def test_validate_rejects_is_ascii_with_non_ascii() -> None:
    with pytest.raises(
        ValidationError, match="must consist of ASCII characters only"
    ):
        StrField(is_ascii=True).validate("Джон")


def test_validate_accepts_is_ascii_with_ascii_only() -> None:
    StrField(is_ascii=True).validate("John")


def test_validate_rejects_char_not_in_allowlist() -> None:
    with pytest.raises(
        ValidationError, match="characters outside the allowed set"
    ):
        StrField(char_list=(True, "qwerty")).validate("qwez")


def test_validate_accepts_value_within_allowlist() -> None:
    StrField(char_list=(True, "qwerty")).validate("qwe")


def test_validate_rejects_char_in_denylist() -> None:
    with pytest.raises(ValidationError, match="contains forbidden characters"):
        StrField(char_list=(False, "!@#$")).validate("abc!")


def test_validate_accepts_value_without_denylisted_chars() -> None:
    StrField(char_list=(False, "!@#$")).validate("abc")
