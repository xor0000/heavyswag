import sys
from typing import NamedTuple

import pytest

from heavyswag._internal._dto import (
    dto_type,
    resolve_dto_fields,
    validate_dto_type,
)
from heavyswag.errors import RouteTreeError
from heavyswag.specify.request import Body, Query, Request


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
