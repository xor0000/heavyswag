import re
import string
from itertools import pairwise
from typing import Literal, NamedTuple

from heavyswag.errors import ValidationError

_PATTERN_PRESETS: dict[str, str] = {
    "email": r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    "url": r"^https?://[^\s/$.?#][^\s]*$",
    "credit_card": r"^\d{13,19}$",
    "phone": r"^\+?\d{7,15}$",
    "slug": r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    "password": r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)\S{8,}$",  # nosec B105 -- a strength-check regex, not a credential
}

_SPECIAL_SYMBOLS = frozenset(string.punctuation)

_MIN_CONSECUTIVE_REPEATS = 2


class StrField(NamedTuple):
    min_len: int | None = None
    max_len: int | None = None
    pattern: str | None = None
    pattern_preset: (
        Literal["email", "url", "credit_card", "phone", "slug", "password"]
        | None
    ) = None
    first_is_upper: bool | None = None
    first_is_lover: bool | None = None
    is_upper: bool | None = None
    is_lower: bool | None = None
    has_uppercase: bool | None = None
    has_lowercase: bool | None = None
    has_digits: bool | None = None
    has_special_symbols: bool | None = None
    min_special_symbols: int | None = None
    has_whitespace: bool | None = None
    strip_whitespace: bool | None = None
    no_leading_trailing_whitespace: bool | None = None
    no_consecutive_repeats: int | None = None
    is_alpha: bool | None = None
    is_alnum: bool | None = None
    is_ascii: bool | None = None
    char_list: tuple[bool, str] | None = None

    def assembly(self) -> None:
        """Consistency check of rules during radix tree construction"""

        self.__validate_length()
        self.__validate_pattern()
        self.__validate_case_conflicts()
        self.__validate_special_symbol_bounds()
        self.__validate_alpha_conflicts()
        self.__validate_repeats()
        self.__validate_char_list()

    def validate(self, value: str) -> None:
        """Runtime validation"""

        if self.strip_whitespace:
            value = value.strip()

        self.__check_length(value)
        self.__check_pattern(value)
        self.__check_case(value)
        self.__check_digits(value)
        self.__check_special_symbols(value)
        self.__check_whitespace(value)
        self.__check_repeats(value)
        self.__check_charset(value)
        self.__check_char_list(value)

    def __validate_length(self) -> None:
        if self.min_len is not None and self.min_len < 0:
            msg = "min_len must not be negative"
            raise ValidationError(msg)
        if self.max_len is not None and self.max_len < 0:
            msg = "max_len must not be negative"
            raise ValidationError(msg)
        if (
            self.min_len is not None
            and self.max_len is not None
            and self.max_len < self.min_len
        ):
            msg = "max_len must be greater than or equal to min_len"
            raise ValidationError(msg)

    def __validate_pattern(self) -> None:
        if self.pattern_preset is not None:
            if self.pattern_preset not in _PATTERN_PRESETS:
                msg = f"Unknown pattern_preset: {self.pattern_preset!r}"
                raise ValidationError(msg)
            other_fields = {
                name: value
                for name, value in self._asdict().items()
                if name != "pattern_preset"
            }
            if any(value is not None for value in other_fields.values()):
                msg = "pattern_preset must be set without any other StrField fields"
                raise ValidationError(msg)
            return

        if self.pattern is not None:
            try:
                re.compile(self.pattern)
            except re.error as exc:
                msg = f"Invalid pattern: {exc}"
                raise ValidationError(msg) from exc

    def __validate_case_conflicts(self) -> None:
        if self.first_is_upper and self.first_is_lover:
            msg = "first_is_upper and first_is_lover are mutually exclusive"
            raise ValidationError(msg)
        if self.is_upper and self.is_lower:
            msg = "is_upper and is_lower are mutually exclusive"
            raise ValidationError(msg)
        if self.is_upper and self.has_lowercase:
            msg = "is_upper=True is incompatible with has_lowercase=True"
            raise ValidationError(msg)
        if self.is_lower and self.has_uppercase:
            msg = "is_lower=True is incompatible with has_uppercase=True"
            raise ValidationError(msg)

    def __validate_special_symbol_bounds(self) -> None:
        if (
            self.min_special_symbols is not None
            and self.min_special_symbols < 0
        ):
            msg = "min_special_symbols must not be negative"
            raise ValidationError(msg)
        if self.has_special_symbols is False and self.min_special_symbols:
            msg = (
                "has_special_symbols=False is incompatible with "
                "min_special_symbols"
            )
            raise ValidationError(msg)

    def __validate_alpha_conflicts(self) -> None:
        if self.is_alpha and self.has_digits:
            msg = "is_alpha=True is incompatible with has_digits=True"
            raise ValidationError(msg)
        if self.is_alpha and self.has_special_symbols:
            msg = "is_alpha=True is incompatible with has_special_symbols=True"
            raise ValidationError(msg)

    def __validate_repeats(self) -> None:
        if (
            self.no_consecutive_repeats is not None
            and self.no_consecutive_repeats < _MIN_CONSECUTIVE_REPEATS
        ):
            msg = (
                f"no_consecutive_repeats must be at least "
                f"{_MIN_CONSECUTIVE_REPEATS}"
            )
            raise ValidationError(msg)

    def __validate_char_list(self) -> None:
        if self.char_list is None:
            return
        is_allowlist, chars = self.char_list
        if not isinstance(is_allowlist, bool):
            msg = "char_list[0] must be a bool"
            raise ValidationError(msg)
        if not chars:
            msg = "char_list must not contain an empty character set"
            raise ValidationError(msg)

    # runtime

    def __check_length(self, value: str) -> None:
        if self.min_len is not None and len(value) < self.min_len:
            msg = f"String length is less than {self.min_len}"
            raise ValidationError(msg)
        if self.max_len is not None and len(value) > self.max_len:
            msg = f"String length is greater than {self.max_len}"
            raise ValidationError(msg)

    def __check_pattern(self, value: str) -> None:
        pattern = self.pattern
        if pattern is None and self.pattern_preset is not None:
            pattern = _PATTERN_PRESETS[self.pattern_preset]
        if pattern is not None and re.fullmatch(pattern, value) is None:
            msg = "String does not match pattern"
            raise ValidationError(msg)

    def __check_case(self, value: str) -> None:
        if self.first_is_upper and (not value or not value[0].isupper()):
            msg = "First character must be uppercase"
            raise ValidationError(msg)
        if self.first_is_lover and (not value or not value[0].islower()):
            msg = "First character must be lowercase"
            raise ValidationError(msg)
        if self.is_upper and not value.isupper():
            msg = "String must be uppercase"
            raise ValidationError(msg)
        if self.is_lower and not value.islower():
            msg = "String must be lowercase"
            raise ValidationError(msg)
        if self.has_uppercase and not any(c.isupper() for c in value):
            msg = "String must contain an uppercase character"
            raise ValidationError(msg)
        if self.has_lowercase and not any(c.islower() for c in value):
            msg = "String must contain a lowercase character"
            raise ValidationError(msg)

    def __check_digits(self, value: str) -> None:
        digit_count = sum(c.isdigit() for c in value)
        if self.has_digits and digit_count == 0:
            msg = "String must contain digits"
            raise ValidationError(msg)
        if self.has_digits is False and digit_count > 0:
            msg = "String must not contain digits"
            raise ValidationError(msg)

    def __check_special_symbols(self, value: str) -> None:
        special_count = sum(c in _SPECIAL_SYMBOLS for c in value)
        if self.has_special_symbols and special_count == 0:
            msg = "String must contain special symbols"
            raise ValidationError(msg)
        if self.has_special_symbols is False and special_count > 0:
            msg = "String must not contain special symbols"
            raise ValidationError(msg)
        if (
            self.min_special_symbols is not None
            and special_count < self.min_special_symbols
        ):
            msg = (
                f"String must contain at least "
                f"{self.min_special_symbols} special symbols"
            )
            raise ValidationError(msg)

    def __check_whitespace(self, value: str) -> None:
        if self.has_whitespace and not any(c.isspace() for c in value):
            msg = "String must contain whitespace characters"
            raise ValidationError(msg)
        if self.has_whitespace is False and any(c.isspace() for c in value):
            msg = "String must not contain whitespace characters"
            raise ValidationError(msg)
        if self.no_leading_trailing_whitespace and value != value.strip():
            msg = "String must not have leading/trailing whitespace"
            raise ValidationError(msg)

    def __check_repeats(self, value: str) -> None:
        if self.no_consecutive_repeats is None:
            return
        run = 1
        for prev, curr in pairwise(value):
            run = run + 1 if curr == prev else 1
            if run >= self.no_consecutive_repeats:
                msg = (
                    f"String must not contain {self.no_consecutive_repeats} "
                    "identical characters in a row"
                )
                raise ValidationError(msg)

    def __check_charset(self, value: str) -> None:
        if self.is_alpha and not value.isalpha():
            msg = "String must consist of letters only"
            raise ValidationError(msg)
        if self.is_alnum and not value.isalnum():
            msg = "String must consist of letters and digits only"
            raise ValidationError(msg)
        if self.is_ascii and not value.isascii():
            msg = "String must consist of ASCII characters only"
            raise ValidationError(msg)

    def __check_char_list(self, value: str) -> None:
        if self.char_list is None:
            return
        is_allowlist, chars = self.char_list
        allowed = set(chars)
        if is_allowlist:
            if any(c not in allowed for c in value):
                msg = "String contains characters outside the allowed set"
                raise ValidationError(msg)
        elif any(c in allowed for c in value):
            msg = "String contains forbidden characters"
            raise ValidationError(msg)
