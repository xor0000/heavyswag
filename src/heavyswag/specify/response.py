from dataclasses import dataclass

from heavyswag.constants import ALLOWED_TYPES
from heavyswag.specify.cookie import Cookie


@dataclass(slots=True, kw_only=True)
class Response[Content: ALLOWED_TYPES]:
    status_code: int = 200
    headers: set[tuple[str, str]] | None = None
    cookies: set[Cookie] | None = None
    content: Content | None = None

    def set_cookie(self, cookie: Cookie) -> None:
        if self.cookies is None:
            self.cookies = set()

        self.cookies.add(cookie)

    def attach_header(self, key: str, value: str) -> None:
        if self.headers is None:
            self.headers = set()

        self.headers.add((key, value))
