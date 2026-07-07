import json
from typing import Any, Final

from heavyswag.specify.request import Preambule, Request

EXPECTED_COOKIE_PAIR_LENGTH: Final = 2
EXPECTED_HEADER_PAIR_LENGTH: Final = 2


class Serializer:
    def serialize_preambule(self, content: bytes) -> tuple[Preambule, int]:
        preambule = []

        method_start = method_end = 0

        while content[method_end] != ord(" "):
            method_end += 1

        preambule.append(content[method_start:method_end])

        url_start = url_end = method_end + 1

        while content[url_end] != ord(" "):
            url_end += 1

        preambule.append(content[url_start:url_end])

        preambule_offset = url_end

        while content[preambule_offset] != ord("\n"):
            preambule_offset += 1

        return Preambule(
            method=preambule[0],
            url=preambule[1],
        ), preambule_offset + 1

    def serialize_request(
        self, content: bytes, global_offset: int
    ) -> tuple[Request, int]:
        request_offset = 1
        prev_end = curr_end = False

        headers = {}
        cookies = {}

        value_end = -2
        key_start = key_end = value_start = 0
        while not (prev_end and curr_end):
            prev_end = content[request_offset - 1] == ord("\n")
            curr_end = content[request_offset] == ord("\r")

            if content[request_offset] == ord(":"):
                key_start = value_end + 2
                key_end = request_offset

                if content[key_start:key_end] != b"Cookie":
                    value_end = request_offset
                    while content[request_offset] != ord("\r"):
                        value_end += 1
                        request_offset += 1

                    value_start = key_end + 2

                    headers[content[key_start:key_end]] = content[
                        value_start:value_end
                    ]
                else:
                    request_offset += 2
                    while content[request_offset] != ord("\r"):
                        key_start = request_offset

                        while content[request_offset] != ord("="):
                            request_offset += 1

                        key_end = request_offset

                        value_start = request_offset + 1

                        while content[request_offset] not in {
                            ord(";"),
                            ord("\r"),
                        }:
                            request_offset += 1

                        value_end = request_offset

                        cookies[content[key_start:key_end]] = content[
                            value_start:value_end
                        ]

            request_offset += 1

        return Request(
            headers,
            cookies,
        ), request_offset + global_offset

    def serialize_json(self, content: bytes) -> dict[str, Any]:
        return json.loads(content)
