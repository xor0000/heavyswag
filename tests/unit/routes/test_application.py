from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import NamedTuple

import pytest

from heavyswag.errors import HeavySwagError
from heavyswag.middlewares.setups.cors import CORSMiddleware
from heavyswag.middlewares.setups.err_handler import (
    ErrorHandler,
    ErrorHandlingMiddleware,
)
from heavyswag.middlewares.setups.request_logging import LoggingMiddleware
from heavyswag.routes.application import (
    HeavySwag,
    _dto_type,
    _HS_Server,
    _noop_lifespan,
    _reconstruct_head,
    run_app,
)
from heavyswag.routes.router import HeavyRouter
from heavyswag.specify.request import Body, Request
from heavyswag.specify.response import Response
from tests.unit.factories.asgi import ReceiveQueue, SendRecorder, http_scope


class _Empty(NamedTuple):
    pass


def _build_app(**kwargs: object) -> HeavySwag:
    router = HeavyRouter("/")

    @router.get("/")
    async def index(_: Request, __: _Empty) -> str:
        return "ok"

    return HeavySwag(main_router=router, **kwargs)  # type: ignore[arg-type]


def test_heavyswag_defaults() -> None:
    router = HeavyRouter("/")

    app = HeavySwag(main_router=router)

    assert isinstance(app.err_handler, ErrorHandler)
    assert app.middlewares == ()
    assert app.lifespan is _noop_lifespan


def test_run_app_returns_server() -> None:
    app = _build_app()

    server = run_app(app)

    assert isinstance(server, _HS_Server)


@pytest.mark.asyncio
async def test_noop_lifespan_yields_none() -> None:
    app = _build_app()

    async with _noop_lifespan(app) as value:
        assert value is None


def test_assemble_middlewares_adds_defaults_when_missing() -> None:
    app = _build_app()
    server = run_app(app)

    assembled = server._assemble_middlewares(app.err_handler, ())  # noqa: SLF001

    kinds = [type(m) for m in assembled]
    assert CORSMiddleware in kinds
    assert ErrorHandlingMiddleware in kinds
    assert LoggingMiddleware in kinds


def test_assemble_middlewares_respects_custom_instances_and_order() -> None:
    app = _build_app()
    server = run_app(app)
    custom_cors = CORSMiddleware()

    assembled = server._assemble_middlewares(  # noqa: SLF001
        app.err_handler, [custom_cors]
    )

    cors_instances = [m for m in assembled if isinstance(m, CORSMiddleware)]
    assert cors_instances == [custom_cors]
    assert assembled[-1] is custom_cors


def test_dto_type_extracts_second_param() -> None:
    async def controller(_request: Request, _dto: _Empty) -> str:
        return "x"

    assert _dto_type(controller) is _Empty


def test_reconstruct_head_without_query() -> None:
    scope = http_scope(method="GET", path="/hello")

    head = _reconstruct_head(scope)

    assert head.startswith(b"GET /hello HTTP/1.1\r\n")
    assert head.endswith(b"\r\n\r\n")


def test_reconstruct_head_with_query_string() -> None:
    scope = http_scope(method="GET", path="/hello", query_string=b"a=1")

    head = _reconstruct_head(scope)

    assert head.startswith(b"GET /hello?a=1 HTTP/1.1\r\n")


def test_reconstruct_head_recapitalizes_cookie_header() -> None:
    scope = http_scope(headers=[(b"cookie", b"a=1")])

    head = _reconstruct_head(scope)

    assert b"Cookie: a=1\r\n" in head


def test_reconstruct_head_preserves_other_header_casing() -> None:
    scope = http_scope(headers=[(b"content-type", b"application/json")])

    head = _reconstruct_head(scope)

    assert b"content-type: application/json\r\n" in head


@pytest.mark.asyncio
async def test_http_successful_dispatch() -> None:
    app = _build_app()
    server = run_app(app)

    scope = http_scope(method="GET", path="/")
    receive = ReceiveQueue(
        [{"type": "http.request", "body": b"", "more_body": False}]
    )
    send = SendRecorder()

    await server(scope, receive, send)

    assert send.messages[0]["type"] == "http.response.start"
    assert send.messages[0]["status"] == 200  # noqa: PLR2004
    assert send.messages[1]["body"] == b"ok"


@pytest.mark.asyncio
async def test_http_404_for_unknown_path() -> None:
    app = _build_app()
    server = run_app(app)

    scope = http_scope(method="GET", path="/missing")
    receive = ReceiveQueue(
        [{"type": "http.request", "body": b"", "more_body": False}]
    )
    send = SendRecorder()

    await server(scope, receive, send)

    assert send.messages[0]["status"] == 404  # noqa: PLR2004
    assert send.messages[1]["body"] == b"Not Found"


@pytest.mark.asyncio
async def test_http_method_type_request_returns_not_found() -> None:
    app = _build_app()
    server = run_app(app)

    scope = http_scope(method="OPTIONS", path="/")
    receive = ReceiveQueue(
        [{"type": "http.request", "body": b"", "more_body": False}]
    )
    send = SendRecorder()

    await server(scope, receive, send)

    assert send.messages[0]["status"] == 404  # noqa: PLR2004


@pytest.mark.asyncio
async def test_http_unknown_method_returns_400() -> None:
    app = _build_app()
    server = run_app(app)

    scope = http_scope(method="TEAPOT", path="/")
    receive = ReceiveQueue([])
    send = SendRecorder()

    await server(scope, receive, send)

    assert send.messages[0]["status"] == 400  # noqa: PLR2004
    assert send.messages[1]["body"] == b"Unknown HTTP method"


@pytest.mark.asyncio
async def test_http_reads_multi_chunk_body() -> None:
    router = HeavyRouter("/")

    class Payload(NamedTuple):
        text: Body[str]

    @router.post("/echo")
    async def echo(_: Request, dto: Payload) -> str:
        return dto.text

    app = HeavySwag(main_router=router)
    server = run_app(app)

    scope = http_scope(method="POST", path="/echo")
    receive = ReceiveQueue(
        [
            {"type": "http.request", "body": b'{"tex', "more_body": True},
            {
                "type": "http.request",
                "body": b't": "hi"}',
                "more_body": False,
            },
        ]
    )
    send = SendRecorder()

    await server(scope, receive, send)

    assert send.messages[0]["status"] == 200  # noqa: PLR2004
    assert send.messages[1]["body"] == b"hi"


@pytest.mark.asyncio
async def test_http_dispatch_error_goes_through_error_handling() -> None:
    router = HeavyRouter("/")

    @router.get("/boom")
    async def boom(_: Request, __: _Empty) -> str:
        msg = "kaboom"
        raise HeavySwagError(msg)

    app = HeavySwag(main_router=router)
    server = run_app(app)

    scope = http_scope(method="GET", path="/boom")
    receive = ReceiveQueue(
        [{"type": "http.request", "body": b"", "more_body": False}]
    )
    send = SendRecorder()

    await server(scope, receive, send)

    assert send.messages[0]["status"] == 500  # noqa: PLR2004


@pytest.mark.asyncio
async def test_http_response_object_is_used_as_is() -> None:
    router = HeavyRouter("/")

    @router.get("/created")
    async def created(_: Request, __: _Empty) -> Response[str]:
        response: Response[str] = Response(status_code=201)
        response.set_body("created")
        return response

    app = HeavySwag(main_router=router)
    server = run_app(app)

    scope = http_scope(method="GET", path="/created")
    receive = ReceiveQueue(
        [{"type": "http.request", "body": b"", "more_body": False}]
    )
    send = SendRecorder()

    await server(scope, receive, send)

    assert send.messages[0]["status"] == 201  # noqa: PLR2004
    assert send.messages[1]["body"] == b"created"


@pytest.mark.asyncio
async def test_lifespan_startup_and_shutdown_complete() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def lifespan(_app: HeavySwag) -> AsyncIterator[None]:
        events.append("startup")
        yield
        events.append("shutdown")

    app = _build_app(lifespan=lifespan)
    server = run_app(app)

    receive = ReceiveQueue(
        [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    )
    send = SendRecorder()

    await server({"type": "lifespan"}, receive, send)

    assert events == ["startup", "shutdown"]
    assert send.messages[0]["type"] == "lifespan.startup.complete"
    assert send.messages[1]["type"] == "lifespan.shutdown.complete"


@pytest.mark.asyncio
async def test_lifespan_unexpected_first_message_raises() -> None:
    app = _build_app()
    server = run_app(app)

    receive = ReceiveQueue([{"type": "lifespan.shutdown"}])
    send = SendRecorder()

    with pytest.raises(RuntimeError, match=r"lifespan\.startup"):
        await server({"type": "lifespan"}, receive, send)


@pytest.mark.asyncio
async def test_lifespan_unexpected_second_message_raises() -> None:
    app = _build_app()
    server = run_app(app)

    receive = ReceiveQueue(
        [{"type": "lifespan.startup"}, {"type": "lifespan.startup"}]
    )
    send = SendRecorder()

    with pytest.raises(RuntimeError, match=r"lifespan\.shutdown"):
        await server({"type": "lifespan"}, receive, send)


@pytest.mark.asyncio
async def test_lifespan_startup_failure() -> None:
    @asynccontextmanager
    async def lifespan(_app: HeavySwag) -> AsyncIterator[None]:
        msg = "boom"
        raise RuntimeError(msg)
        yield  # pragma: no cover

    app = _build_app(lifespan=lifespan)
    server = run_app(app)

    receive = ReceiveQueue([{"type": "lifespan.startup"}])
    send = SendRecorder()

    await server({"type": "lifespan"}, receive, send)

    assert send.messages[0]["type"] == "lifespan.startup.failed"
    assert "boom" in send.messages[0]["message"]


@pytest.mark.asyncio
async def test_lifespan_shutdown_failure() -> None:
    @asynccontextmanager
    async def lifespan(_app: HeavySwag) -> AsyncIterator[None]:
        yield
        msg = "shutdown boom"
        raise RuntimeError(msg)

    app = _build_app(lifespan=lifespan)
    server = run_app(app)

    receive = ReceiveQueue(
        [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    )
    send = SendRecorder()

    await server({"type": "lifespan"}, receive, send)

    assert send.messages[0]["type"] == "lifespan.startup.complete"
    assert send.messages[1]["type"] == "lifespan.shutdown.failed"
    assert "shutdown boom" in send.messages[1]["message"]


@pytest.mark.asyncio
async def test_unknown_scope_type_does_nothing() -> None:
    app = _build_app()
    server = run_app(app)

    send = SendRecorder()
    receive = ReceiveQueue([])

    await server({"type": "websocket"}, receive, send)

    assert send.messages == []
