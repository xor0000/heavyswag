from typing import Any, Mapping

from heavyswag.errors import HeavySwagError, SerializationError
from heavyswag.middlewares.base import CallNext, RequestContext
from heavyswag.specify.response import Response


class ErrorHandler:
    """Maps exception types to (status_code, message) pairs.

    Lookup walks the exception's MRO, so registering a base error
    class also covers its subclasses. Anything unregistered (and
    not a subclass of a registered class) falls back to 500, so a
    request can never leak an unhandled exception to the client.
    """

    __slots__ = ("_map_errors",)

    def __init__(
        self,
        map_errors: Mapping[type[Exception], tuple[int, str]] | None = None,
    ) -> None:
        self._map_errors: dict[type[Exception], tuple[int, str]] = {
            HeavySwagError: (500, "Internal Server Error"),
            SerializationError: (400, "Bad Request"),
            **(map_errors or {}),
        }

    def __call__(self, exc: Exception) -> Response[str]:
        status_code, message = self._resolve(type(exc))

        response: Response[str] = Response(status_code=status_code)
        response.set_body(message)
        return response

    def _resolve(self, exc_type: type[Exception]) -> tuple[int, str]:
        for klass in exc_type.__mro__:
            mapped = self._map_errors.get(klass)
            if mapped is not None:
                return mapped

        return 500, "Internal Server Error"


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
