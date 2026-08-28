from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, cast

from httpx import ASGITransport, AsyncClient

from heavyswag.routes.application import (
    HeavySwag,
    Receive,
    Scope,
    Send,
    run_app,
)

__all__ = ("run_test",)


def run_test(
    app: HeavySwag, *, base_url: str = "http://test"
) -> "AsyncClient":
    server = run_app(app)

    async def asgi_app(
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[MutableMapping[str, Any]]],
        send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
    ) -> None:
        await server(
            cast("Scope", scope),
            cast("Receive", receive),
            cast("Send", send),
        )

    return AsyncClient(base_url=base_url, transport=ASGITransport(asgi_app))
