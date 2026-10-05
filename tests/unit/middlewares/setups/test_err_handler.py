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
    assert response.body == "Internal Server Error"


def test_default_mapping_for_serialization_error() -> None:
    handler = ErrorHandler()

    response = handler(SerializationError("bad input"))

    assert response.status_code == 400  # noqa: PLR2004
    assert response.body == "Bad Request"


def test_unmapped_subclass_falls_back_to_registered_ancestor() -> None:
    handler = ErrorHandler()

    response = handler(RouteTreeError("boom"))

    assert response.status_code == 500  # noqa: PLR2004


def test_unregistered_exception_falls_back_to_hardcoded_default() -> None:
    handler = ErrorHandler()

    response = handler(ValueError("nope"))

    assert response.status_code == 500  # noqa: PLR2004
    assert response.body == "Internal Server Error"


def test_custom_mapping_overrides_default() -> None:
    class OutOfStockError(HeavySwagError):
        pass

    handler = ErrorHandler(map_errors={OutOfStockError: (409, "Out of Stock")})

    response = handler(OutOfStockError("nope"))

    assert response.status_code == 409  # noqa: PLR2004
    assert response.body == "Out of Stock"


@pytest.mark.asyncio
async def test_middleware_passes_through_successful_response() -> None:
    middleware = ErrorHandlingMiddleware(ErrorHandler())

    async def handler(_context: RequestContext) -> Response[str]:
        response: Response[str] = Response()
        response.set_body("ok")
        return response

    response = await middleware(handler, _context())

    assert response.body == "ok"


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


def _error_body(exc: Exception, status_code: int, message: str) -> _ErrorBody:  # noqa: ARG001
    return _ErrorBody(code=type(exc).__name__, message=message)


def test_body_factory_builds_structured_error_body() -> None:
    handler = ErrorHandler(body=_error_body)

    response = handler(SerializationError("bad input"))

    assert response.status_code == 400  # noqa: PLR2004
    assert response.body == _ErrorBody("SerializationError", "Bad Request")
    assert handler.body_type is _ErrorBody


def test_without_body_factory_body_type_is_none() -> None:
    assert ErrorHandler().body_type is None


def test_body_factory_without_return_annotation_is_rejected() -> None:
    with pytest.raises(HeavySwagError, match="must annotate its return type"):
        ErrorHandler(body=lambda exc, status, message: _ErrorBody("", ""))  # noqa: ARG005


def test_body_factory_returning_non_namedtuple_is_rejected() -> None:
    def body(exc: Exception, status_code: int, message: str) -> str:  # noqa: ARG001
        return message

    with pytest.raises(HeavySwagError, match="as a NamedTuple"):
        ErrorHandler(body=body)  # type: ignore[arg-type]


def test_lookup_returns_none_for_unregistered_exception() -> None:
    handler = ErrorHandler()

    assert handler.lookup(ValueError) is None
    assert handler.resolve(ValueError) == (500, "Internal Server Error")


def test_lookup_walks_mro() -> None:
    handler = ErrorHandler()

    assert handler.lookup(RouteTreeError) == (500, "Internal Server Error")
