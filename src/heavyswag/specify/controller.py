from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any, Concatenate, Protocol

from heavyswag.constants import ALLOWED_TYPES
from heavyswag.specify.request import Request
from heavyswag.specify.response import Response

if TYPE_CHECKING:
    from heavyswag.middlewares.base import Middleware


type Controller[
    InDTO: tuple[ALLOWED_TYPES, ...] | None,
    OutDTO: ALLOWED_TYPES | tuple[ALLOWED_TYPES, ...],
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
