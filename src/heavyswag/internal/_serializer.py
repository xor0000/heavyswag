from heavyswag.specify.request import Request


class Serializer:
    def serialize_request(self, content: bytes) -> Request:
        message = content.split(b"\r\n")

        headers = {}
        cookies = {}
        for header in message[1:]:
            if header == b"":
                break
            key, value = [x.decode() for x in header.split(b":")]
            if key == "Cookie":
                request_cookies = value.split(";")
                for cookie in request_cookies:
                    cookie_key, cookie_value = cookie.split("=")
                    cookies[cookie_key.strip()] = cookie_value.strip()

            headers[key] = value.strip()

        return Request(
            headers=headers,
            cookies=cookies,
        )
