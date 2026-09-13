import sys
from dataclasses import dataclass
from typing import NamedTuple

import pytest

from heavyswag._internal._dto import (
    dto_type,
    output_dto_type,
    resolve_dto_fields,
    validate_dto_type,
    validate_output_dto_type,
)
from heavyswag.errors import RouteTreeError
from heavyswag.specify.request import Body, Query, Request
from heavyswag.specify.response import Response


class _Mixed(NamedTuple):
    item_id: int
    flag: Query[bool] | None
    name: Body[str] | None
    label: str


def test_resolve_dto_fields_marks_optional_and_strips_none() -> None:
    fields = {field.name: field for field in resolve_dto_fields(_Mixed)}

    assert fields["item_id"].optional is False
    assert fields["item_id"].target is int

    assert fields["flag"].optional is True
    assert fields["flag"].target is bool

    assert fields["name"].optional is True
    assert fields["name"].target is str

    assert fields["label"].optional is False
    assert fields["label"].target is str


def test_validate_dto_type_allows_optional_body_and_query() -> None:
    validate_dto_type(_Mixed)


def test_validate_dto_type_rejects_default_value() -> None:
    class _WithDefault(NamedTuple):
        value: Body[str] | None = None

    with pytest.raises(
        RouteTreeError, match="must not declare default values"
    ):
        validate_dto_type(_WithDefault)


def test_validate_dto_type_rejects_optional_path_param() -> None:
    class _OptionalPath(NamedTuple):
        item_id: str | None

    with pytest.raises(RouteTreeError, match="must not be Optional"):
        validate_dto_type(_OptionalPath)


def test_validate_dto_type_allows_empty_dto() -> None:
    class _Empty(NamedTuple):
        pass

    validate_dto_type(_Empty)

    if sys.version_info >= (3, 14):
        validate_dto_type(tuple[()])


def test_dto_type_extracts_second_param() -> None:
    class _Empty(NamedTuple):
        pass

    async def controller(_request: Request, _dto: _Empty) -> str:
        return "x"

    assert dto_type(controller) is _Empty


def test_validate_dto_type_allows_nested_namedtuple_body() -> None:
    class _Inner(NamedTuple):
        value: Body[str]

    class _Outer(NamedTuple):
        value: Body[_Inner]

    validate_dto_type(_Outer)


def test_validate_dto_type_allows_bare_fields_in_nested_body() -> None:
    """A bare field inside a `Body[NamedTuple]` target is read
    straight off the nested JSON object, exactly like a `Body[...]`
    field would be — there's no path or query string down there to
    tell them apart, so both are legal. This is also what lets a
    request DTO double as a nested response DTO without a separate,
    marker-free copy.
    """

    class _Inner(NamedTuple):
        value1: Body[str]
        value2: str

    class _Outer(NamedTuple):
        details: Body[_Inner]

    validate_dto_type(_Outer)


def test_validate_dto_type_rejects_dataclass_nested_body() -> None:
    @dataclass
    class _NotANamedTuple:
        value: str

    class _Bad(NamedTuple):
        value: Body[_NotANamedTuple]

    with pytest.raises(RouteTreeError, match="must be a NamedTuple"):
        validate_dto_type(_Bad)


def test_validate_dto_type_rejects_plain_class_nested_body() -> None:
    class _NotANamedTuple:
        def __init__(self, value: str) -> None:
            self.value = value

    class _Bad(NamedTuple):
        value: Body[_NotANamedTuple]

    with pytest.raises(RouteTreeError, match="must be a NamedTuple"):
        validate_dto_type(_Bad)


def test_validate_dto_type_rejects_namedtuple_path_param() -> None:
    class _Inner(NamedTuple):
        value: Body[str]

    class _Bad(NamedTuple):
        item: _Inner

    with pytest.raises(
        RouteTreeError, match=r"path parameter.*must not be a NamedTuple"
    ):
        validate_dto_type(_Bad)


def test_validate_dto_type_rejects_namedtuple_query_param() -> None:
    class _Inner(NamedTuple):
        value: Body[str]

    class _Bad(NamedTuple):
        item: Query[_Inner]

    with pytest.raises(
        RouteTreeError, match=r"query parameter.*must not be a NamedTuple"
    ):
        validate_dto_type(_Bad)


def test_validate_dto_type_allows_mixed_markers_at_top_level() -> None:
    """A DTO with path/query/body fields side by side is fine as a
    top-level (controller-facing) DTO — the no-Query rule below only
    kicks in once it's nested inside another DTO's `Body[...]`.
    """

    class _TopLevelMixed(NamedTuple):
        value1: Body[str]
        value2: Query[str]
        value3: str

    validate_dto_type(_TopLevelMixed)


def test_validate_dto_type_rejects_nested_body_with_query_field() -> None:
    """`Body[X]` only makes sense if nothing in `X` is `Query[...]` —
    there's no query string inside a JSON object to resolve it from.
    A bare field, unlike `Query[...]`, is fine (see the 'allows bare
    fields' test above).
    """

    class _WithQuery(NamedTuple):
        value1: Body[str]
        value2: Query[str]

    class _Outer(NamedTuple):
        details: Body[_WithQuery]

    with pytest.raises(RouteTreeError, match="must not use Query fields"):
        validate_dto_type(_Outer)


def test_validate_dto_type_allows_nested_pure_body_next_to_mixed_top_level() -> (
    None
):
    class _PureBody(NamedTuple):
        value1: Body[str]
        value2: Body[str]
        value3: Body[str]

    class _Outer(NamedTuple):
        value1: Body[str]
        value2: Query[str]
        value3: str
        details: Body[_PureBody]

    validate_dto_type(_Outer)


def test_validate_dto_type_rejects_impure_nested_body_next_to_pure_sibling() -> (
    None
):
    """The same DTO can carry one valid nested `Body[...]` field and
    one invalid one — each nested target is checked independently.
    """

    class _WithQuery(NamedTuple):
        value1: Body[str]
        value2: Query[str]

    class _PureBody(NamedTuple):
        value1: Body[str]
        value2: Body[str]
        value3: Body[str]

    class _Outer(NamedTuple):
        value1: Body[str]
        value2: Query[str]
        value3: str
        details: Body[_WithQuery]
        details2: Body[_PureBody]

    with pytest.raises(RouteTreeError, match="must not use Query fields"):
        validate_dto_type(_Outer)


def test_validate_dto_type_rejects_deeply_nested_query_field() -> None:
    """The no-Query rule is checked all the way down, not just one
    level — `_Outer` nests `_Mid` nests `_WithQuery`, and
    `_WithQuery`'s `Query[...]` field is what makes the whole chain
    invalid.
    """

    class _WithQuery(NamedTuple):
        value: Query[str]

    class _Mid(NamedTuple):
        value: Body[_WithQuery]

    class _Outer(NamedTuple):
        value: Body[_Mid]

    with pytest.raises(RouteTreeError, match="must not use Query fields"):
        validate_dto_type(_Outer)


def test_validate_dto_type_allows_deeply_nested_bare_fields() -> None:
    """The mirror image of the test above: bare fields all the way
    down are fine, since none of them is `Query[...]`.
    """

    class _Leaf(NamedTuple):
        value: str

    class _Mid(NamedTuple):
        value: Body[_Leaf]

    class _Outer(NamedTuple):
        value: Body[_Mid]

    validate_dto_type(_Outer)


def test_validate_dto_type_rejects_body_without_type_parameter() -> None:
    """`Body` (bare, no `[X]`) leaves the field's target as the
    marker's own unbound `TypeVar` — that's not a type `_coerce`
    could ever build a value from, so it must be caught here rather
    than surfacing as a confusing `SerializationError` mid-request.
    """

    class _Bad(NamedTuple):
        value: Body

    with pytest.raises(RouteTreeError, match="without a type parameter"):
        validate_dto_type(_Bad)


def test_validate_dto_type_rejects_query_without_type_parameter() -> None:
    class _Bad(NamedTuple):
        value: Query

    with pytest.raises(RouteTreeError, match="without a type parameter"):
        validate_dto_type(_Bad)


def test_validate_dto_type_rejects_nested_body_without_type_parameter() -> (
    None
):
    """The same mistake one level down — inside a `Body[NamedTuple]`
    target — is still a shape problem `_has_no_query_fields` must
    catch, not something that reaches `_coerce` at request time.
    """

    class _Inner(NamedTuple):
        value: Body

    class _Outer(NamedTuple):
        details: Body[_Inner]

    with pytest.raises(RouteTreeError, match="must not use Query fields"):
        validate_dto_type(_Outer)


def test_validate_dto_type_allows_generic_alias_target() -> None:
    """A field target like `list[str]` is a `types.GenericAlias`, not
    a plain `type` — `_validate_field_shape` only inspects plain
    classes (the `NamedTuple`-vs-scalar distinction doesn't apply to
    a generic), so it must return without raising here.
    """

    class _WithList(NamedTuple):
        tags: Query[list[str]]

    validate_dto_type(_WithList)


def test_validate_output_dto_type_allows_body_marker() -> None:
    """A response DTO is always serialized whole into the body, so a
    `Body[...]` marker on one of its fields is redundant, but
    harmless — it's not rejected, precisely so a request DTO can
    double as a nested response DTO without needing a separate,
    marker-free copy (see `_has_no_query_fields`'s docstring).
    """

    class _Out(NamedTuple):
        value: Body[str]

    validate_output_dto_type(_Out)


def test_validate_output_dto_type_rejects_query_marker() -> None:
    """Unlike `Body`, a `Query` marker can never be honored on the
    way out — a response has no query string to resolve it from.
    """

    class _Out(NamedTuple):
        value: Query[str]

    with pytest.raises(RouteTreeError, match="Query marker"):
        validate_output_dto_type(_Out)


def test_validate_output_dto_type_allows_unmarked_fields() -> None:
    class _Out(NamedTuple):
        id: str
        name: str
        tags: list[str]

    validate_output_dto_type(_Out)


def test_validate_output_dto_type_allows_body_marker_in_nested_namedtuple() -> (
    None
):
    """The `Body`-is-fine rule applies recursively too — a nested
    `NamedTuple` field carrying `Body[...]` is still just a key in
    the same response body.
    """

    class _Inner(NamedTuple):
        value: Body[str]

    class _Out(NamedTuple):
        inner: _Inner

    validate_output_dto_type(_Out)


def test_validate_output_dto_type_rejects_query_marker_in_nested_namedtuple() -> (
    None
):
    """The no-Query rule applies recursively — a nested `NamedTuple`
    field is still part of the same response body.
    """

    class _Inner(NamedTuple):
        value: Query[str]

    class _Out(NamedTuple):
        inner: _Inner

    with pytest.raises(RouteTreeError, match="Query marker"):
        validate_output_dto_type(_Out)


def test_output_dto_type_extracts_bare_return_type() -> None:
    class _Empty(NamedTuple):
        pass

    class _Out(NamedTuple):
        value: str

    async def controller(_request: Request, _dto: _Empty) -> _Out:
        return _Out(value="x")

    assert output_dto_type(controller) is _Out


def test_output_dto_type_unwraps_response() -> None:
    class _Empty(NamedTuple):
        pass

    class _Out(NamedTuple):
        value: str

    async def controller(_request: Request, _dto: _Empty) -> Response[_Out]:
        return Response()

    assert output_dto_type(controller) is _Out


def test_output_dto_type_passthrough_for_scalar_response() -> None:
    class _Empty(NamedTuple):
        pass

    async def controller(_request: Request, _dto: _Empty) -> Response[str]:
        return Response()

    assert output_dto_type(controller) is str
