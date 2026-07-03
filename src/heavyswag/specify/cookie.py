from datetime import datetime
from enum import StrEnum
from typing import NamedTuple, Self


class SameSite(StrEnum):
    STRICT = "Strict"
    LAX = "Lax"
    NONE = "None"


class Cookie(NamedTuple):
    """
    Cookies (used only when setting cookies in the response)
    In requests, cookies are represented as a standard dict[str, str]

    :param
        - max_age: seconds; takes precedence over expiration
    """

    key: str
    value: str
    max_age: int | None = None
    expires: datetime | None = None
    domain: str | None = None
    path: str | None = "/"
    secure: bool = False
    http_only: bool = True
    same_site: SameSite | None = SameSite.LAX
    partitioned: bool = False

    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other: Self) -> bool:  # type: ignore[override]
        return self.key == other.key
