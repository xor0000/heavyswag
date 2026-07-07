import json
from typing import Any


class RequestFactory:
    @classmethod
    def build(
        cls,
        url: str = "/",
        method: str = "GET",
        body: dict[str, Any] | None = None,
        cookies: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        headers = dict(headers or {})
        cookies = cookies or {}

        body_bytes = b""
        if body is not None:
            body_bytes = json.dumps(body, separators=(",", ":")).encode(
                "utf-8"
            )

        if cookies:
            headers["Cookie"] = "; ".join(
                f"{name}={value}" for name, value in cookies.items()
            )

        request = (
            f"{method.upper()} {url} HTTP/1.1\r\n"
            + "".join(
                f"{name}: {value}\r\n" for name, value in headers.items()
            )
            + "\r\n"
        ).encode("ascii")

        return request + body_bytes
