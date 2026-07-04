import json
from typing import Any

from heavyswag.http import Method
from tests.unit.factories.common import generate_random_string


class RequestFactory:
    @classmethod
    def build(
        cls,
        url: str = generate_random_string(),
        method: Method | str = Method.GET,
        body: dict[str, Any] | None = None,
        cookies: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        http_headers = (
            (
                "\r\n".join(
                    [f"{key}: {value}" for key, value in headers.items()]
                )
            )
            + "\r\n"
            if headers is not None
            else ""
        )
        http_cookies = (
            f"Cookie: {'; '.join([f'{key}={value}' for key, value in cookies.items()])}\r\n"
            if cookies is not None
            else ""
        )
        if body is None:
            body = {}

        return f"{method.value if isinstance(method, Method) else method} {url} HTTP/1.1\r\n{http_headers}{http_cookies}\r\n{json.dumps(body)}"
