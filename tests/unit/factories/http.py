from http import HTTPMethod

from tests.unit.factories.common import generate_random_string


class RequestFactory:
    @classmethod
    def build(
        cls,
        url: str = generate_random_string(),
        method: HTTPMethod = HTTPMethod.GET,
        cookies: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        http_headers = (
            "\r\n".join([f"{key}: {value}" for key, value in headers.items()])
            if headers is not None
            else ""
        )
        http_cookies = (
            f"Cookie: {'; '.join([f'{key}={value}' for key, value in cookies.items()])}\r\n"
            if cookies is not None
            else ""
        )

        return f"{method.value} /{url} HTTP/1.1\r\n{http_headers}\r\n{http_cookies}"
