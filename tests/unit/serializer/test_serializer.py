from datetime import datetime
from typing import NamedTuple
from uuid import UUID

import pytest

from heavyswag._internal._serializer import Serializer
from heavyswag.constants import HttpMethod
from heavyswag.errors import SerializationError
from heavyswag.specify.cookie import Cookie, SameSite
from heavyswag.specify.request import Body, Preambule, Query, Request
from heavyswag.specify.response import Response
from tests.unit.factories.http import RequestFactory


def test_parse_http_without_header_and_cookies_and_body() -> None:
    serializer = Serializer(RequestFactory.build())

    preambule = serializer.serialize_preambule()
    request = serializer.serialize_request()

    assert preambule == Preambule(url="/", method=HttpMethod.GET)
    assert request == Request(
        headers=[],
        cookies=[],
    )


def test_parse_http_with_header_without_cookies_and_body() -> None:
    serializer = Serializer(RequestFactory.build(headers={"foo": "bar"}))

    preambule = serializer.serialize_preambule()
    request = serializer.serialize_request()

    assert preambule == Preambule(url="/", method=HttpMethod.GET)
    assert request == Request(
        headers=[("foo", "bar")],
        cookies=[],
    )


def test_parse_http_with_header_and_cookies_without_body() -> None:
    serializer = Serializer(
        RequestFactory.build(headers={"foo": "bar"}, cookies={"bar": "foo"})
    )

    preambule = serializer.serialize_preambule()
    request = serializer.serialize_request()

    assert preambule == Preambule(url="/", method=HttpMethod.GET)
    assert request == Request(
        headers=[("foo", "bar")],
        cookies=[("bar", "foo")],
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
        headers=[("foo", "bar")],
        cookies=[("bar", "foo"), ("baz", "qux")],
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
        headers=[("foo", "bar")],
        cookies=[("bar", "foo")],
    )
    assert body == {"foo": [1, 2, 3]}


def test_parse_http_with_query_string() -> None:
    serializer = Serializer(RequestFactory.build(url="/search?q=cats"))

    preambule = serializer.serialize_preambule()

    assert preambule == Preambule(
        url="/search", method=HttpMethod.GET, query="q=cats"
    )


def test_append_body_extends_buffer() -> None:
    serializer = Serializer(b"head-")
    serializer.append_body(b"tail")

    assert serializer._request == b"head-tail"  # noqa: SLF001


def test_append_body_ignores_empty_chunk() -> None:
    serializer = Serializer(b"only")
    serializer.append_body(b"")

    assert serializer._request == b"only"  # noqa: SLF001


def test_serialize_json_malformed_raises() -> None:
    serializer = Serializer(b"not json")

    with pytest.raises(SerializationError, match="Malformed JSON body"):
        serializer.serialize_json()


def test_serialize_json_non_object_raises() -> None:
    serializer = Serializer(b"[1, 2, 3]")

    with pytest.raises(SerializationError, match="must be an object"):
        serializer.serialize_json()


class _PathOnly(NamedTuple):
    item_id: str


class _QueryOnly(NamedTuple):
    flag: Query[bool]


class _BodyOnly(NamedTuple):
    name: Body[str]


class _Mixed(NamedTuple):
    item_id: int
    flag: Query[bool]
    name: Body[str]


class _TwoBodyFields(NamedTuple):
    a: Body[str]
    b: Body[str]


class _OptionalBody(NamedTuple):
    name: Body[str] | None


class _OptionalQuery(NamedTuple):
    flag: Query[bool] | None


class _QueryScalarTypes(NamedTuple):
    as_str: Query[str]
    as_int: Query[int]
    as_float: Query[float]
    as_bool: Query[bool]
    as_uuid: Query[UUID]
    as_datetime: Query[datetime]
    as_bytes: Query[bytes]


class _QueryListStr(NamedTuple):
    tags: Query[list[str]]


class _QueryListInt(NamedTuple):
    ids: Query[list[int]]


class _OptionalQueryListStr(NamedTuple):
    tags: Query[list[str]] | None


def test_serialize_dto_path_param() -> None:
    serializer = Serializer(b"")

    dto = serializer.serialize_dto(_PathOnly, {"item_id": "abc"}, {})

    assert dto == _PathOnly(item_id="abc")


def test_serialize_dto_query_param() -> None:
    serializer = Serializer(b"")

    dto = serializer.serialize_dto(_QueryOnly, {}, {"flag": ["true"]})

    assert dto == _QueryOnly(flag=True)


def test_serialize_dto_query_supports_scalar_types() -> None:
    serializer = Serializer(b"")
    query_params = {
        "as_str": ["hello"],
        "as_int": ["5"],
        "as_float": ["5.5"],
        "as_bool": ["true"],
        "as_uuid": ["12345678-1234-5678-1234-567812345678"],
        "as_datetime": ["2026-01-01T12:00:00"],
        "as_bytes": ["hi"],
    }

    dto = serializer.serialize_dto(_QueryScalarTypes, {}, query_params)

    assert dto == _QueryScalarTypes(
        as_str="hello",
        as_int=5,
        as_float=5.5,
        as_bool=True,
        as_uuid=UUID("12345678-1234-5678-1234-567812345678"),
        as_datetime=datetime(2026, 1, 1, 12, 0, 0),  # noqa: DTZ001
        as_bytes=b"hi",
    )


def test_serialize_dto_query_scalar_field_rejects_repeated_key() -> None:
    """`?a="123"&a="123"&...` against a non-list `Query[X]` field
    has no single sane value to pick, so it's a bad request instead
    of silently keeping the first or last one.
    """
    serializer = Serializer(b"")
    query_params = serializer.parse_query(
        'a="123"&a="123"&a="123"&a="123"&a="123"'
    )

    class _ScalarField(NamedTuple):
        a: Query[str]

    with pytest.raises(SerializationError, match="repeated 5 times"):
        serializer.serialize_dto(_ScalarField, {}, query_params)


def test_serialize_dto_query_list_str_collects_repeated_key() -> None:
    """`?a="123"&a="123"&...` against `Query[list[str]]` collects
    every repeat, each coerced to `str`.
    """
    serializer = Serializer(b"")
    query_params = serializer.parse_query(
        'a="123"&a="123"&a="123"&a="123"&a="123"'
    )

    class _ListField(NamedTuple):
        a: Query[list[str]]

    dto = serializer.serialize_dto(_ListField, {}, query_params)

    assert dto == _ListField(a=['"123"'] * 5)


def test_serialize_dto_query_list_int_collects_repeated_key_coerced() -> None:
    """The same repeated key against `Query[list[int]]` coerces
    each item to `int` instead of leaving them as strings.
    """
    serializer = Serializer(b"")
    query_params = serializer.parse_query(
        "ids=123&ids=123&ids=123&ids=123&ids=123"
    )

    dto = serializer.serialize_dto(_QueryListInt, {}, query_params)

    assert dto == _QueryListInt(ids=[123, 123, 123, 123, 123])


def test_serialize_dto_query_list_str_single_value_is_still_a_list() -> None:
    serializer = Serializer(b"")

    dto = serializer.serialize_dto(_QueryListStr, {}, {"tags": ["value"]})

    assert dto == _QueryListStr(tags=["value"])


def test_serialize_dto_query_list_float_coerces_each_item() -> None:
    class _ListFloat(NamedTuple):
        values: Query[list[float]]

    serializer = Serializer(b"")

    dto = serializer.serialize_dto(
        _ListFloat, {}, {"values": ["1.5", "2.5", "3.5"]}
    )

    assert dto == _ListFloat(values=[1.5, 2.5, 3.5])


def test_serialize_dto_optional_query_list_str_present_value() -> None:
    serializer = Serializer(b"")

    dto = serializer.serialize_dto(
        _OptionalQueryListStr, {}, {"tags": ["a", "b"]}
    )

    assert dto == _OptionalQueryListStr(tags=["a", "b"])


def test_serialize_dto_optional_query_list_str_missing_key_is_none() -> None:
    serializer = Serializer(b"")

    dto = serializer.serialize_dto(_OptionalQueryListStr, {}, {})

    assert dto == _OptionalQueryListStr(tags=None)


def test_serialize_dto_body_field() -> None:
    serializer = Serializer(b'{"name": "max"}')

    dto = serializer.serialize_dto(_BodyOnly, {}, {})

    assert dto == _BodyOnly(name="max")


def test_serialize_dto_mixed_fields() -> None:
    serializer = Serializer(b'{"name": "max"}')

    dto = serializer.serialize_dto(_Mixed, {"item_id": "5"}, {"flag": ["1"]})

    expected = _Mixed(item_id=5, flag=True, name="max")
    assert dto == expected


def test_serialize_dto_missing_path_param_raises() -> None:
    serializer = Serializer(b"")

    with pytest.raises(SerializationError, match="Missing field 'item_id'"):
        serializer.serialize_dto(_PathOnly, {}, {})


def test_serialize_dto_missing_query_param_raises() -> None:
    serializer = Serializer(b"")

    with pytest.raises(SerializationError, match="Missing field 'flag'"):
        serializer.serialize_dto(_QueryOnly, {}, {})


def test_serialize_dto_missing_body_field_raises() -> None:
    serializer = Serializer(b"{}")

    with pytest.raises(SerializationError, match="Missing field 'name'"):
        serializer.serialize_dto(_BodyOnly, {}, {})


def test_serialize_dto_optional_body_explicit_null_is_none() -> None:
    serializer = Serializer(b'{"name": null}')

    dto = serializer.serialize_dto(_OptionalBody, {}, {})

    assert dto == _OptionalBody(name=None)


def test_serialize_dto_optional_body_missing_key_raises() -> None:
    serializer = Serializer(b"{}")

    with pytest.raises(SerializationError, match="Missing field 'name'"):
        serializer.serialize_dto(_OptionalBody, {}, {})


def test_serialize_dto_optional_body_present_value_is_coerced() -> None:
    serializer = Serializer(b'{"name": "max"}')

    dto = serializer.serialize_dto(_OptionalBody, {}, {})

    assert dto == _OptionalBody(name="max")


def test_serialize_dto_optional_query_missing_key_is_none() -> None:
    serializer = Serializer(b"")

    dto = serializer.serialize_dto(_OptionalQuery, {}, {})

    assert dto == _OptionalQuery(flag=None)


def test_serialize_dto_optional_query_present_value_is_coerced() -> None:
    serializer = Serializer(b"")

    dto = serializer.serialize_dto(_OptionalQuery, {}, {"flag": ["true"]})

    assert dto == _OptionalQuery(flag=True)


def test_serialize_dto_parses_body_once_for_multiple_fields() -> None:
    serializer = Serializer(b'{"a": "1", "b": "2"}')

    dto = serializer.serialize_dto(_TwoBodyFields, {}, {})

    assert dto == _TwoBodyFields(a="1", b="2")


def test_parse_query_empty() -> None:
    serializer = Serializer(b"")

    assert serializer.parse_query("") == {}


def test_parse_query_single_pair() -> None:
    serializer = Serializer(b"")

    assert serializer.parse_query("a=1") == {"a": ["1"]}


def test_parse_query_multiple_pairs() -> None:
    serializer = Serializer(b"")

    assert serializer.parse_query("a=1&b=2") == {"a": ["1"], "b": ["2"]}


def test_parse_query_pair_without_value() -> None:
    serializer = Serializer(b"")

    assert serializer.parse_query("flag") == {"flag": [""]}


def test_parse_query_repeated_key_collects_all_values() -> None:
    serializer = Serializer(b"")

    assert serializer.parse_query("a=1&a=2&a=3") == {"a": ["1", "2", "3"]}


def test_wrap_response_passthrough() -> None:
    serializer = Serializer(b"")
    response: Response[str] = Response(status_code=201)
    response.set_body("hi")

    assert serializer.wrap_response(response) is response


def test_wrap_response_wraps_bare_value() -> None:
    serializer = Serializer(b"")

    wrapped = serializer.wrap_response("hello")

    assert isinstance(wrapped, Response)
    assert wrapped.body == "hello"
    assert wrapped.status_code == 200  # noqa: PLR2004


def test_render_body_none() -> None:
    serializer = Serializer(b"")

    assert serializer.render_body(None) == b""


def test_render_body_bytes_passthrough() -> None:
    serializer = Serializer(b"")

    assert serializer.render_body(b"raw") == b"raw"


def test_render_body_str_encodes() -> None:
    serializer = Serializer(b"")

    assert serializer.render_body("hi") == b"hi"


def test_render_body_json_encodes_other_types() -> None:
    serializer = Serializer(b"")

    assert serializer.render_body({"a": 1}) == b'{"a": 1}'


def test_render_cookie_minimal() -> None:
    serializer = Serializer(b"")
    cookie = Cookie(
        key="k",
        value="v",
        path=None,
        http_only=False,
        same_site=None,
    )

    assert serializer.render_cookie(cookie) == "k=v"


def test_render_cookie_full() -> None:
    serializer = Serializer(b"")
    cookie = Cookie(
        key="k",
        value="v",
        max_age=60,
        expires=datetime(2026, 1, 1, 12, 0, 0),  # noqa: DTZ001
        domain="example.com",
        path="/",
        secure=True,
        http_only=True,
        same_site=SameSite.STRICT,
        partitioned=True,
    )

    rendered = serializer.render_cookie(cookie)

    assert rendered == (
        "k=v; Max-Age=60; Expires=Thu, 01 Jan 2026 12:00:00 GMT; "
        "Domain=example.com; Path=/; Secure; HttpOnly; "
        "SameSite=Strict; Partitioned"
    )


def test_render_includes_headers_and_cookies() -> None:
    serializer = Serializer(b"")
    response: Response[str] = Response(status_code=200)
    response.set_body("ok")
    response.attach_header("X-Test", "1")
    response.set_cookie(Cookie(key="k", value="v"))

    headers, body = serializer.render(response)

    assert body == b"ok"
    assert (b"X-Test", b"1") in headers
    assert any(name == b"set-cookie" for name, _ in headers)
    assert any(name == b"content-length" for name, _ in headers)


def test_render_no_content_length_for_204() -> None:
    serializer = Serializer(b"")
    response: Response[str] = Response(status_code=204)
    response.set_body("ignored")

    headers, _ = serializer.render(response)

    assert not any(name == b"content-length" for name, _ in headers)


def test_render_no_content_length_for_empty_body() -> None:
    serializer = Serializer(b"")
    response: Response[str] = Response(status_code=200)

    headers, body = serializer.render(response)

    assert body == b""
    assert not any(name == b"content-length" for name, _ in headers)


def test_to_jsonable_uuid() -> None:
    serializer = Serializer(b"")
    value = UUID("12345678-1234-5678-1234-567812345678")

    assert serializer._to_jsonable(value) == str(value)  # noqa: SLF001


def test_to_jsonable_datetime() -> None:
    serializer = Serializer(b"")
    dt = datetime(2026, 1, 1, 12, 0, 0)  # noqa: DTZ001

    assert serializer._to_jsonable(dt) == dt.isoformat()  # noqa: SLF001


def test_to_jsonable_bytes() -> None:
    serializer = Serializer(b"")

    assert serializer._to_jsonable(b"hi") == "hi"  # noqa: SLF001


def test_to_jsonable_namedtuple() -> None:
    class Point(NamedTuple):
        x: int
        y: int

    serializer = Serializer(b"")

    assert serializer._to_jsonable(Point(1, 2)) == {"x": 1, "y": 2}  # noqa: SLF001


def test_to_jsonable_nested_namedtuple_with_uuid() -> None:
    class Nested(NamedTuple):
        id: UUID

    serializer = Serializer(b"")
    value = Nested(id=UUID("12345678-1234-5678-1234-567812345678"))

    assert serializer._to_jsonable(value) == {"id": str(value.id)}  # noqa: SLF001


def test_to_jsonable_list_and_tuple() -> None:
    serializer = Serializer(b"")

    assert serializer._to_jsonable([1, "a"]) == [1, "a"]  # noqa: SLF001
    assert serializer._to_jsonable((1, "a")) == [1, "a"]  # noqa: SLF001


def test_to_jsonable_dict() -> None:
    serializer = Serializer(b"")

    assert serializer._to_jsonable({"a": 1}) == {"a": 1}  # noqa: SLF001


def test_to_jsonable_passthrough_scalar() -> None:
    serializer = Serializer(b"")

    assert serializer._to_jsonable(42) == 42  # noqa: SLF001, PLR2004
    assert serializer._to_jsonable(None) is None  # noqa: SLF001


def test_field_returns_value() -> None:
    serializer = Serializer(b"")

    assert serializer._field({"a": 1}, "a", dict) == 1  # noqa: SLF001


def test_field_missing_raises() -> None:
    serializer = Serializer(b"")

    with pytest.raises(SerializationError, match="Missing field 'a'"):
        serializer._field({}, "a", _PathOnly)  # noqa: SLF001


def test_coerce_matches_origin_passthrough() -> None:
    serializer = Serializer(b"")

    assert serializer._coerce(5, int) == 5  # noqa: SLF001, PLR2004


def test_coerce_bool_leak_guard() -> None:
    serializer = Serializer(b"")
    leaked_bool = True

    with pytest.raises(SerializationError, match="Cannot coerce"):
        serializer._coerce(leaked_bool, int)  # noqa: SLF001


def test_coerce_str_fallback() -> None:
    serializer = Serializer(b"")

    assert serializer._coerce("5", int) == 5  # noqa: SLF001, PLR2004


def test_coerce_unmatched_non_str_raises() -> None:
    serializer = Serializer(b"")

    with pytest.raises(SerializationError, match="Cannot coerce"):
        serializer._coerce(None, str)  # noqa: SLF001


def test_coerce_generic_origin_passthrough() -> None:
    serializer = Serializer(b"")

    assert serializer._coerce([1, 2], list[int]) == [1, 2]  # noqa: SLF001


@pytest.mark.parametrize(
    ("raw", "target", "expected"),
    [
        ("5", int, 5),
        ("5.5", float, 5.5),
        ("true", bool, True),
        ("false", bool, False),
        ("hello", str, "hello"),
    ],
)
def test_coerce_str_scalar_types(
    raw: str,
    target: type,
    expected: object,
) -> None:
    serializer = Serializer(b"")

    assert serializer._coerce_str(raw, target) == expected  # noqa: SLF001


def test_coerce_str_uuid() -> None:
    serializer = Serializer(b"")
    value = "12345678-1234-5678-1234-567812345678"

    assert serializer._coerce_str(value, UUID) == UUID(value)  # noqa: SLF001


def test_coerce_str_datetime() -> None:
    serializer = Serializer(b"")

    result = serializer._coerce_str("2026-01-01T12:00:00", datetime)  # noqa: SLF001

    assert result == datetime(2026, 1, 1, 12, 0, 0)  # noqa: DTZ001


def test_coerce_str_bytes() -> None:
    serializer = Serializer(b"")

    assert serializer._coerce_str("hi", bytes) == b"hi"  # noqa: SLF001


def test_coerce_str_invalid_int_raises() -> None:
    serializer = Serializer(b"")

    with pytest.raises(SerializationError, match="Cannot parse"):
        serializer._coerce_str("abc", int)  # noqa: SLF001


def test_coerce_str_invalid_uuid_raises() -> None:
    serializer = Serializer(b"")

    with pytest.raises(SerializationError, match="Cannot parse"):
        serializer._coerce_str("not-a-uuid", UUID)  # noqa: SLF001


def test_coerce_str_invalid_datetime_raises() -> None:
    serializer = Serializer(b"")

    with pytest.raises(SerializationError, match="Cannot parse"):
        serializer._coerce_str("not-a-date", datetime)  # noqa: SLF001


def test_coerce_str_unsupported_type_raises() -> None:
    serializer = Serializer(b"")

    with pytest.raises(SerializationError, match="Unsupported target type"):
        serializer._coerce_str("x", list)  # noqa: SLF001
