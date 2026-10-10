from collections.abc import Callable, Mapping
from typing import Any, NamedTuple, get_type_hints

from heavyswag._internal._dto import is_namedtuple, validate_output_dto_type
from heavyswag.errors import (
    HeavySwagError,
    SerializationError,
    ValidationError,
)
from heavyswag.middlewares.base import CallNext, RequestContext
from heavyswag.specify.response import Response

type ErrorBody = Callable[[Exception, int, str], NamedTuple]

_FALLBACK: tuple[int, str] = (500, "Internal Server Error")


class ErrorHandler:
    """Maps exception types to (status_code, message) pairs.

    Lookup walks the exception's MRO, so registering a base error
    class also covers its subclasses. Anything unregistered (and
    not a subclass of a registered class) falls back to 500, so a
    request can never leak an unhandled exception to the client.

    By default the body is the plain-text message. `body` swaps that
    for one structured envelope shared by every error:
    `body(exc, status_code, message)` returns a `NamedTuple`, sent as
    JSON. It must annotate its return type — that's the schema
    `heavyswag.doc` documents every error response with.
    """

    __slots__ = ("_body", "_map_errors", "body_type")

    def __init__(
        self,
        map_errors: Mapping[type[Exception], tuple[int, str]] | None = None,
        body: ErrorBody | None = None,
    ) -> None:
        self._map_errors: dict[type[Exception], tuple[int, str]] = {
            HeavySwagError: _FALLBACK,
            SerializationError: (400, "Bad Request"),
            ValidationError: (400, "Bad Request"),
            **(map_errors or {}),
        }
        self._body = body
        self.body_type: type[tuple[Any, ...]] | None = (
            None if body is None else _body_type(body)
        )

    def __call__(self, exc: Exception) -> Response[Any]:
        status_code, message = self.resolve(type(exc))

        response: Response[Any] = Response(status_code=status_code)
        response.set_body(self.build_body(exc, status_code, message))
        return response

    def build_body(
        self, exc: Exception, status_code: int, message: str
    ) -> Any:  # noqa: ANN401
        """What `__call__` would send for `exc` — `heavyswag.doc` uses
        it to render an example error body."""
        if self._body is None:
            return message

        return self._body(exc, status_code, message)

    def resolve(self, exc_type: type[Exception]) -> tuple[int, str]:
        return self.lookup(exc_type) or _FALLBACK

    def lookup(self, exc_type: type[Exception]) -> tuple[int, str] | None:
        """Like `resolve`, but `None` for an exception nothing is
        registered for — rather than the hardcoded 500 fallback."""
        for klass in exc_type.__mro__:
            mapped = self._map_errors.get(klass)
            if mapped is not None:
                return mapped

        return None


def _body_type(body: ErrorBody) -> type[tuple[Any, ...]]:
    try:
        return_type = get_type_hints(body).get("return")
    except (NameError, TypeError):
        return_type = None

    if not is_namedtuple(return_type):
        msg = (
            "ErrorHandler body factory must annotate its return type "
            f"as a NamedTuple, got {return_type!r}."
        )
        raise HeavySwagError(msg)

    validate_output_dto_type(return_type)
    return return_type


class ErrorHandlingMiddleware:
    """Catches exceptions from the rest of the chain and converts
    them into a Response via `ErrorHandler`, so a bug in a
    controller or a downstream middleware never reaches the ASGI
    boundary as a raw exception.
    """

    __slots__ = ("_err_handler",)

    def __init__(self, err_handler: ErrorHandler) -> None:
        self._err_handler = err_handler

    async def __call__(
        self,
        call_next: CallNext,
        context: RequestContext,
    ) -> Response[Any]:
        try:
            return await call_next(context)
        except Exception as exc:  # noqa: BLE001
            return self._err_handler(exc)
