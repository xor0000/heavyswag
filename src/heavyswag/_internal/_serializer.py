import json
from typing import Any, Final

from heavyswag.http import Method
from heavyswag.specify.request import Preambule, Request

CR: Final = ord("\r")
LF: Final = ord("\n")
SP: Final = ord(" ")
DC: Final = ord("=")
SC: Final = ord(";")
CN: Final = ord(":")


class Serializer:
    def __init__(self, request: bytes) -> None:
        self._request = request
        self._offset = 0

    def serialize_preambule(self) -> Preambule:
        method_start = method_end = self._offset

        while self._request[method_end] != SP:
            method_end += 1

        method = Method[(self._request[method_start:method_end]).decode()]

        url_start = url_end = method_end + 1

        while self._request[url_end] != SP:
            url_end += 1

        url = self._request[url_start:url_end].decode()

        self._offset = url_end

        while self._request[self._offset] != LF:
            self._offset += 1

        return Preambule(
            url,
            method,
        )

    def serialize_request(self) -> Request:
        headers: dict[str, str] = {}
        cookies: dict[str, str] = {}

        value_end = self._offset - 1
        key_start = key_end = value_start = self._offset
        while self._request[self._offset : self._offset + 2] != b"\r\n":
            if self._request[self._offset] == CN:
                key_start = value_end + 2
                key_end = self._offset

                if self._request[key_start:key_end] != b"Cookie":
                    value_end = self._offset
                    while self._request[self._offset] != CR:
                        value_end += 1
                        self._offset += 1

                    value_start = key_end + 2

                    headers[self._request[key_start:key_end].decode()] = (
                        self._request[value_start:value_end].decode()
                    )
                else:
                    self._offset += 2
                    while self._request[self._offset] != CR:
                        key_start = self._offset

                        while self._request[self._offset] != DC:
                            self._offset += 1

                        key_end = self._offset

                        value_start = self._offset + 1

                        while self._request[self._offset] not in {
                            SC,
                            CR,
                        }:
                            self._offset += 1

                        value_end = self._offset

                        if self._request[self._offset] == SC:
                            self._offset += 2

                        cookies[self._request[key_start:key_end].decode()] = (
                            self._request[value_start:value_end].decode()
                        )

            self._offset += 1

        return Request(
            headers,
            cookies,
        )

    def serialize_json(self) -> dict[str, Any]:
        return json.loads(self._request[self._offset :])  # type: ignore[no-any-return]
