import pytest

from heavyswag._internal._serializer import Serializer
from heavyswag.constants import HttpMethod
from heavyswag.middlewares.base import (
    CallNext,
    RequestContext,
    build_middlewares,
)
from heavyswag.specify.request import Preambule, Request
from heavyswag.specify.response import Response


def _make_context() -> RequestContext:
    return RequestContext(
        preambule=Preambule(url="/", method=HttpMethod.GET),
        request=Request(headers=[], cookies=[]),
        serializer=Serializer(b""),
    )


@pytest.mark.asyncio
async def test_build_middlewares_with_no_middlewares_calls_func_directly() -> (
    None
):
    async def handler(_context: RequestContext) -> Response[str]:
        response: Response[str] = Response()
        response.content = "direct"
        return response

    chain = build_middlewares((), handler)

    response = await chain(_make_context())

    assert response.content == "direct"


@pytest.mark.asyncio
async def test_build_middlewares_wraps_in_registration_order() -> None:
    calls: list[str] = []

    async def handler(_context: RequestContext) -> Response[str]:
        calls.append("handler")
        response: Response[str] = Response()
        response.content = "done"
        return response

    async def outer(
        call_next: CallNext, context: RequestContext
    ) -> Response[str]:
        calls.append("outer-before")
        response = await call_next(context)
        calls.append("outer-after")
        return response

    async def inner(
        call_next: CallNext, context: RequestContext
    ) -> Response[str]:
        calls.append("inner-before")
        response = await call_next(context)
        calls.append("inner-after")
        return response

    chain = build_middlewares((outer, inner), handler)

    response = await chain(_make_context())

    assert response.content == "done"
    assert calls == [
        "outer-before",
        "inner-before",
        "handler",
        "inner-after",
        "outer-after",
    ]
