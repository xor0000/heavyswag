from heavyswag.internal._serializer import Serializer
from heavyswag.specify.request import Request
from tests.unit.factories import RequestFactory


def test_serialize_http_request_without_cookies_and_headers() -> None:
    request = RequestFactory.build().encode()

    serializer = Serializer()

    assert serializer.serialize_request(request) == Request(
        headers={},
        cookies={},
    )


def test_serialize_http_request_with_cookies_and_headers() -> None:
    request = RequestFactory.build(
        headers={
            "header-a": "header-1",
            "header-b": "header-2",
            "header-c": "header-3",
        },
        cookies={
            "cookie-a": "cookie-1",
            "cookie-b": "cookie-2",
            "cookie-c": "cookie-3",
        },
    ).encode()

    serializer = Serializer()

    assert serializer.serialize_request(request) == Request(
        headers={
            "header-a": "header-1",
            "header-b": "header-2",
            "header-c": "header-3",
            "Cookie": "cookie-a=cookie-1; cookie-b=cookie-2; cookie-c=cookie-3",
        },
        cookies={
            "cookie-a": "cookie-1",
            "cookie-b": "cookie-2",
            "cookie-c": "cookie-3",
        },
    )
