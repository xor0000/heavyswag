from typing import Final

from heavyswag.exceptions import (
    UnprocessableCookieFormatError,
    UnprocessableHeadersFormatError,
)
from heavyswag.specify.request import Request

EXPECTED_COOKIE_PAIR_LENGTH: Final = 2
EXPECTED_HEADER_PAIR_LENGTH: Final = 2


class Serializer:
    def serialize_request(self, content: bytes) -> Request:
        message = content.split(b"\r\n")

        headers = {}
        cookies = {}
        for header in message[1:]:
            if header == b"":
                break
            header_pair = [x.decode() for x in header.split(b":")]
            if len(header_pair) != EXPECTED_HEADER_PAIR_LENGTH:
                msg = "Unprocessable headers format"
                raise UnprocessableHeadersFormatError(msg)

            key, value = header_pair
            if key == "Cookie":
                request_cookies = value.split(";")
                for cookie in request_cookies:
                    cookie_pair = cookie.split("=")
                    if len(cookie_pair) != EXPECTED_COOKIE_PAIR_LENGTH:
                        msg = "Unprocessable cookie format"
                        raise UnprocessableCookieFormatError(msg)

                    cookie_key, cookie_value = cookie_pair
                    cookies[cookie_key.strip()] = cookie_value.strip()

            headers[key] = value.strip()

        return Request(
            headers=headers,
            cookies=cookies,
        )
