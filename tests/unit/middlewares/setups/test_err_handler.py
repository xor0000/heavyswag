from typing import NamedTuple

import pytest

from heavyswag._internal._serializer import Serializer
from heavyswag.constants import HttpMethod
from heavyswag.errors import HeavySwagError, RouteTreeError, SerializationError
from heavyswag.middlewares.base import RequestContext
from heavyswag.middlewares.setups.err_handler import (
    ErrorHandler,
    ErrorHandlingMiddleware,
)
from heavyswag.specify.request import Preambule, Request
from heavyswag.specify.response import Response


def _context() -> RequestContext:
    return RequestContext(
        preambule=Preambule(url="/", method=HttpMethod.GET),
        request=Request(headers=[], cookies=[]),
        serializer=Serializer(b""),
    )


def test_default_mapping_for_base_error() -> None:
    handler = ErrorHandler()

    response = handler(HeavySwagError("boom"))

    assert response.status_code == 500  # noqa: PLR2004
    assert response.content == "Internal Server Error"


def test_default_mapping_for_serialization_error() -> None:
    handler = ErrorHandler()

    response = handler(SerializationError("bad input"))

    assert response.status_code == 400  # noqa: PLR2004
    assert response.content == "Bad Request"


def test_unmapped_subclass_falls_back_to_registered_ancestor() -> None:
    handler = ErrorHandler()

    response = handler(RouteTreeError("boom"))

    assert response.status_code == 500  # noqa: PLR2004


def test_unregistered_exception_falls_back_to_hardcoded_default() -> None:
    handler = ErrorHandler()

    response = handler(ValueError("nope"))

    assert response.status_code == 500  # noqa: PLR2004
    assert response.content == "Internal Server Error"


def test_custom_mapping_overrides_default() -> None:
    class OutOfStockError(HeavySwagError):
        pass

    handler = ErrorHandler(map_errors={OutOfStockError: (409, "Out of Stock")})

    response = handler(OutOfStockError("nope"))

    assert response.status_code == 409  # noqa: PLR2004
    assert response.content == "Out of Stock"


@pytest.mark.asyncio
async def test_middleware_passes_through_successful_response() -> None:
    middleware = ErrorHandlingMiddleware(ErrorHandler())

    async def handler(_context: RequestContext) -> Response[str]:
        response: Response[str] = Response()
        response.content = "ok"
        return response

    response = await middleware(handler, _context())

    assert response.content == "ok"


@pytest.mark.asyncio
async def test_middleware_catches_exception_and_maps_it() -> None:
    middleware = ErrorHandlingMiddleware(ErrorHandler())

    async def handler(_context: RequestContext) -> Response[str]:
        msg = "bad"
        raise SerializationError(msg)

    response = await middleware(handler, _context())

    assert response.status_code == 400  # noqa: PLR2004


class _ErrorBody(NamedTuple):
    code: str
    message: str


def _error_schema(
    exc: Exception,
    status_code: int,  # noqa: ARG001
    message: str,
) -> _ErrorBody:
    return _ErrorBody(code=type(exc).__name__, message=message)


def test_schema_factory_builds_structured_error_body() -> None:
    handler = ErrorHandler(schema=_error_schema)

    response = handler(SerializationError("bad input"))

    assert response.status_code == 400  # noqa: PLR2004
    assert response.content == _ErrorBody("SerializationError", "Bad Request")
    assert handler.schema_type is _ErrorBody


def test_without_schema_factory_schema_type_is_none() -> None:
    assert ErrorHandler().schema_type is None


def test_schema_factory_without_return_annotation_is_rejected() -> None:
    with pytest.raises(HeavySwagError, match="must annotate its return type"):
        ErrorHandler(schema=lambda exc, status, message: _ErrorBody("", ""))  # noqa: ARG005


def test_schema_factory_returning_non_namedtuple_is_rejected() -> None:
    def schema(exc: Exception, status_code: int, message: str) -> str:  # noqa: ARG001
        return message

    with pytest.raises(HeavySwagError, match="as a NamedTuple"):
        ErrorHandler(schema=schema)  # type: ignore[arg-type]


def test_lookup_returns_none_for_unregistered_exception() -> None:
    handler = ErrorHandler()

    assert handler.lookup(ValueError) is None
    assert handler.resolve(ValueError) == (500, "Internal Server Error")


def test_lookup_walks_mro() -> None:
    handler = ErrorHandler()

    assert handler.lookup(RouteTreeError) == (500, "Internal Server Error")


def test_schema_factory_with_unresolvable_annotation_is_rejected() -> None:
    def schema(exc: Exception, status_code: int, message: str) -> "NotDefined":  # type: ignore[name-defined]  # noqa: F821
        raise NotImplementedError

    with pytest.raises(HeavySwagError, match="must annotate its return type"):
        ErrorHandler(schema=schema)
