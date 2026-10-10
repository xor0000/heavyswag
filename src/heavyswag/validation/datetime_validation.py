from datetime import datetime
from typing import NamedTuple

from heavyswag.errors import ValidationError


class DateTimeField(NamedTuple):
    min: datetime | None = None
    max: datetime | None = None
    require_tz: bool | None = None
    is_past: bool | None = None
    is_future: bool | None = None

    def assembly(self) -> None:
        """Consistency check of rules during radix tree construction"""

        self.__validate_bounds()
        self.__validate_relative_time_conflict()

    def validate(self, value: datetime) -> None:
        """Runtime validation"""

        self.__check_tz(value)
        self.__check_bounds(value)
        self.__check_relative_time(value)

    def __validate_bounds(self) -> None:
        if (
            self.min is not None
            and self.max is not None
            and self.max < self.min
        ):
            msg = "max must be greater than or equal to min"
            raise ValidationError(msg)

    def __validate_relative_time_conflict(self) -> None:
        if self.is_past and self.is_future:
            msg = "is_past and is_future are mutually exclusive"
            raise ValidationError(msg)

    def __check_tz(self, value: datetime) -> None:
        if self.require_tz and value.tzinfo is None:
            msg = "Value must be timezone-aware"
            raise ValidationError(msg)

    def __check_bounds(self, value: datetime) -> None:
        if self.min is not None and value < self.min:
            msg = f"Value is earlier than {self.min.isoformat()}"
            raise ValidationError(msg)
        if self.max is not None and value > self.max:
            msg = f"Value is later than {self.max.isoformat()}"
            raise ValidationError(msg)

    def __check_relative_time(self, value: datetime) -> None:
        now = datetime.now(value.tzinfo)
        if self.is_past and value >= now:
            msg = "Value must be in the past"
            raise ValidationError(msg)
        if self.is_future and value <= now:
            msg = "Value must be in the future"
            raise ValidationError(msg)
