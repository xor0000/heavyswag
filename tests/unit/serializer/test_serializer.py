from heavyswag._internal._serializer import Serializer
from heavyswag.constants import HttpMethod
from heavyswag.specify.request import Preambule, Request
from tests.unit.factories.http import RequestFactory


def test_parse_http_without_header_and_cookies_and_body() -> None:
    serializer = Serializer(RequestFactory.build())

    preambule = serializer.serialize_preambule()
    request = serializer.serialize_request()

    assert preambule == Preambule(url="/", method=HttpMethod.GET)
    assert request == Request(
        headers={},
        cookies={},
    )


def test_parse_http_with_header_without_cookies_and_body() -> None:
    serializer = Serializer(RequestFactory.build(headers={"foo": "bar"}))

    preambule = serializer.serialize_preambule()
    request = serializer.serialize_request()

    assert preambule == Preambule(url="/", method=HttpMethod.GET)
    assert request == Request(
        headers={"foo": "bar"},
        cookies={},
    )


def test_parse_http_with_header_and_cookies_without_body() -> None:
    serializer = Serializer(
        RequestFactory.build(headers={"foo": "bar"}, cookies={"bar": "foo"})
    )

    preambule = serializer.serialize_preambule()
    request = serializer.serialize_request()

    assert preambule == Preambule(url="/", method=HttpMethod.GET)
    assert request == Request(
        headers={"foo": "bar"},
        cookies={"bar": "foo"},
    )


def test_parse_http_with_header_and_multiple_cookies_without_body() -> None:
    serializer = Serializer(
        RequestFactory.build(
            headers={"foo": "bar"}, cookies={"bar": "foo", "baz": "qux"}
        )
    )

    preambule = serializer.serialize_preambule()
    request = serializer.serialize_request()

    assert preambule == Preambule(url="/", method=HttpMethod.GET)
    assert request == Request(
        headers={"foo": "bar"},
        cookies={"bar": "foo", "baz": "qux"},
    )


def test_parse_http_with_header_and_cookies_and_body() -> None:
    serializer = Serializer(
        RequestFactory.build(
            headers={"foo": "bar"},
            cookies={"bar": "foo"},
            body={"foo": [1, 2, 3]},
        )
    )

    preambule = serializer.serialize_preambule()
    request = serializer.serialize_request()
    body = serializer.serialize_json()

    assert preambule == Preambule(url="/", method=HttpMethod.GET)
    assert request == Request(
        headers={"foo": "bar"},
        cookies={"bar": "foo"},
    )
    assert body == {"foo": [1, 2, 3]}
