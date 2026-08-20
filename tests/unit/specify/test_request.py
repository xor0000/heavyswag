from typing import Annotated, get_args, get_origin, get_type_hints

from heavyswag.specify.request import (
    Body,
    BodyMarker,
    Query,
    QueryMarker,
    Request,
)


def test_marker_repr() -> None:
    assert repr(BodyMarker()) == "<Marker 'body'>"
    assert repr(QueryMarker()) == "<Marker 'query'>"


def test_body_marker_extraction() -> None:
    class A: ...

    def controller(dto: Body[A]) -> None: ...

    hint = get_type_hints(controller, include_extras=True)["dto"]
    target, *metadata = get_args(hint)

    assert get_origin(hint) is Annotated
    assert target is A
    assert any(isinstance(marker, BodyMarker) for marker in metadata)


def test_query_marker_extraction() -> None:
    class A: ...

    def controller(dto: Query[A]) -> None: ...

    hint = get_type_hints(controller, include_extras=True)["dto"]
    target, *metadata = get_args(hint)

    assert get_origin(hint) is Annotated
    assert target is A
    assert any(isinstance(marker, QueryMarker) for marker in metadata)


def test_request_shape() -> None:
    req = Request(
        headers=[("content-type", "application/json")],
        cookies=[],
    )

    assert ("content-type", "application/json") in req.headers
    assert req.cookies == []


def test_request_accepts_list_inputs() -> None:
    req = Request(headers=[("content-type", "application/json")], cookies=[])

    assert req.headers == [("content-type", "application/json")]
    assert req.cookies == []


def test_request_defaults_to_empty_collections() -> None:
    req = Request([], [])

    assert req.headers == []
    assert req.cookies == []
