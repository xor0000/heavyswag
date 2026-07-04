from typing import get_args, get_origin, get_type_hints

from heavyswag.http import Method
from heavyswag.specify.request import Body, Query, Request


def test_body_marker_extraction() -> None:
    class A: ...

    def controller(dto: Body[A]) -> None: ...

    hint = get_type_hints(controller)["dto"]

    assert get_origin(hint) is Body
    assert get_args(hint) == (A,)


def test_query_marker_extraction() -> None:
    class A: ...

    def controller(dto: Query[A]) -> None: ...

    hint = get_type_hints(controller)["dto"]

    assert get_origin(hint) is Query
    assert get_args(hint) == (A,)


def test_request_shape() -> None:
    req = Request(
        url="/users",
        method=Method.GET,
        body={},
        headers={"content-type": "application/json"},
        cookies={},
    )
    assert req.headers["content-type"] == "application/json"
    assert req.cookies == {}
