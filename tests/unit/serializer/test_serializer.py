import pytest

from heavyswag.exceptions import (
    UnprocessableCookieFormatError,
    UnprocessableHeadersFormatError,
    UnsupportedHTTPMethodError,
)
from heavyswag.http import Method
from heavyswag.internal._serializer import Serializer
from heavyswag.specify.request import Request
from tests.unit.factories import RequestFactory


def test_serialize_http_request_without_cookies_and_headers() -> None:
    request = RequestFactory.build(url="/users").encode()

    serializer = Serializer()

    assert serializer.serialize_request(request) == Request(
        url="/users",
        method=Method.GET,
        body={},
        headers={},
        cookies={},
    )


def test_serialize_http_request_with_cookies_and_headers() -> None:
    request = RequestFactory.build(
        url="/users",
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
        url="/users",
        method=Method.GET,
        body={},
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


def test_serialize_http_request_with_wrong_header_format() -> None:
    request = RequestFactory.build(
        headers={
            "header-a:": "header-1",
            "header-b": "header-2",
            "header-c": "header-3",
        },
    ).encode()

    serializer = Serializer()

    with pytest.raises(UnprocessableHeadersFormatError):
        assert serializer.serialize_request(request)


def test_serialize_http_request_with_wrong_cookie_value_format() -> None:
    request = RequestFactory.build(
        cookies={
            "cookie-a": "cookie-1",
            "cookie-b": "=cookie-2",
            "cookie-c": "cookie-3",
        },
    ).encode()

    serializer = Serializer()

    with pytest.raises(UnprocessableCookieFormatError):
        assert serializer.serialize_request(request)


def test_serialize_http_request_with_unsupported_http_method() -> None:
    request = RequestFactory.build(method="PODSFG").encode()

    serializer = Serializer()

    with pytest.raises(UnsupportedHTTPMethodError):
        assert serializer.serialize_request(request)


def test_serialize_http_request_with_json_body() -> None:
    request = RequestFactory.build(
        url="/users",
        method="POST",
        body={"body_param_a": 1, "body_param_b": 2, "body_param_c": 3},
    ).encode()

    serializer = Serializer()

    assert serializer.serialize_request(request) == Request(
        url="/users",
        method=Method.POST,
        body={"body_param_a": 1, "body_param_b": 2, "body_param_c": 3},
        headers={},
        cookies={},
    )
