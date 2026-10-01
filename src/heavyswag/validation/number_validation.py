from typing import NamedTuple

from heavyswag.errors import ValidationError


class NumField[T: float](NamedTuple):
    min: T | None = None
    max: T | None = None
    is_even: bool | None = None
    is_odd: bool | None = None

    def assembly(self) -> None:
        """Consistency check of rules during radix tree construction"""

        self.__validate_bounds()
        self.__validate_parity_conflict()

    def validate(self, value: T) -> None:
        """Runtime validation"""

        self.__check_bounds(value)
        self.__check_parity(value)

    def __validate_bounds(self) -> None:
        if (
            self.min is not None
            and self.max is not None
            and self.max < self.min
        ):
            msg = "max must be greater than or equal to min"
            raise ValidationError(msg)

    def __validate_parity_conflict(self) -> None:
        if self.is_even and self.is_odd:
            msg = "is_even and is_odd are mutually exclusive"
            raise ValidationError(msg)

    def __check_bounds(self, value: T) -> None:
        if self.min is not None and value < self.min:
            msg = f"Value is less than {self.min}"
            raise ValidationError(msg)
        if self.max is not None and value > self.max:
            msg = f"Value is greater than {self.max}"
            raise ValidationError(msg)

    def __check_parity(self, value: T) -> None:
        if self.is_even and value % 2 != 0:
            msg = "Value must be even"
            raise ValidationError(msg)
        if self.is_odd and value % 2 == 0:
            msg = "Value must be odd"
            raise ValidationError(msg)
