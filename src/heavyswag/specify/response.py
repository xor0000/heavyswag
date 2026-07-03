from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

from heavyswag.specify.cookie import Cookie

if TYPE_CHECKING:
    from typing import NamedTuple, Sequence
    from uuid import UUID

    type Scalar = int | float | str | bool | UUID | NamedTuple
    type Body = Scalar | Sequence[Scalar]


@dataclass(slots=True, kw_only=True)
class Response:
    status_code: int = 200
    header: set[tuple[str, str]] | None = None
    cookie: set[Cookie] | None = None
    body: Body | None = None

    def set_cookie(self, cookie: Cookie) -> None:
        if self.cookie is None:
            self.cookie = set()

        self.cookie.add(cookie)

    def attach_header(self, key: str, value: str) -> None:
        if self.header is None:
            self.header = set()

        self.header.add((key, value))

    def set_body(self, body: Body) -> None:
        self.body = body
