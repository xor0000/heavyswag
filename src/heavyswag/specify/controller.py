from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any, Concatenate, Protocol

from heavyswag.constants import ALLOWED_TYPES
from heavyswag.specify.request import Request
from heavyswag.specify.response import Response

if TYPE_CHECKING:
    # `middlewares.base` imports the serializer, which imports
    # `heavyswag.specify` — only the annotation needs it.
    from heavyswag.middlewares.base import Middleware

# The shape of every route handler: the parsed `Request`, the DTO built
# from the path / query / body, and a DTO (or a `Response` carrying one)
# back. Lives here, next to `Request` and `Response`, rather than in the
# router — so anything that needs to talk about a controller can, without
# depending on `heavyswag.routes`.
type Controller[
    InDTO: tuple[ALLOWED_TYPES, ...] | None,
    OutDTO: ALLOWED_TYPES | tuple[ALLOWED_TYPES, ...] | None,
    **P,
] = Callable[
    Concatenate[Request, InDTO, P], Awaitable[OutDTO | Response[OutDTO]]  # type: ignore[type-var]
]


class DependencyResolver(Protocol):
    """The hook a DI container plugs into (`HeavySwag(di_resolver=...)`)"""

    def wrap_controller(
        self, controller: Controller[Any, Any, Any]
    ) -> Callable[[Request, Any], Awaitable[Any]]: ...

    def wrap_middleware(
        self, middleware: "type[Middleware]"
    ) -> "Middleware": ...

    def request_scope(
        self, request: Request
    ) -> AbstractAsyncContextManager[None]: ...
