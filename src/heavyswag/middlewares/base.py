from collections.abc import Awaitable, Callable, Sequence
from functools import partial
from typing import Any, NamedTuple, Protocol

from heavyswag._internal._serializer import Serializer
from heavyswag.specify.request import Preambule, Request
from heavyswag.specify.response import Response


class RequestContext(NamedTuple):
    preambule: Preambule
    request: Request
    serializer: Serializer


type CallNext = Callable[[RequestContext], Awaitable[Response[Any]]]


class Middleware(Protocol):
    async def __call__(
        self,
        call_next: CallNext,
        context: RequestContext,
    ) -> Response[Any]: ...


def build_middlewares(
    middlewares: Sequence[Middleware],
    /,
    func: Callable[[RequestContext], Awaitable[Response[Any]]],
) -> CallNext:
    chain = func
    for middleware in reversed(middlewares):
        chain = partial(middleware, chain)

    return chain
