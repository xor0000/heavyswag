from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import partial
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Mapping,
    Sequence,
    get_type_hints,
)

from heavyswag._internal._serializer import Serializer
from heavyswag.constants import HttpMethod
from heavyswag.middlewares.base import (
    Middleware,
    RequestContext,
    build_middlewares,
)
from heavyswag.middlewares.setups.cors import CORSMiddleware

from heavyswag.middlewares.setups.err_handler import (
    ErrorHandler,
    ErrorHandlingMiddleware,
)
from heavyswag.middlewares.setups.request_logging import LoggingMiddleware
from heavyswag.routes.radix_tree import CompressedRadixTree
from heavyswag.routes.router import HeavyRouter
from heavyswag.specify.response import Response

type Message = dict[str, Any]
type Scope = dict[str, Any]
type Receive = Callable[[], Awaitable[Message]]
type Send = Callable[[Message], Awaitable[None]]

type Lifespan = Callable[
    ["HeavySwag"],
    AbstractAsyncContextManager[Mapping[str, Any] | None],
]


@asynccontextmanager
async def _noop_lifespan(app: "HeavySwag") -> AsyncIterator[None]:  # noqa: ARG001
    yield None


class HeavySwag:
    __slots__ = (
        "dependency_resolver",
        "err_handler",
        "lifespan",
        "main_router",
        "middlewares",
    )

    def __init__(
        self,
        main_router: HeavyRouter,
        err_handler: ErrorHandler | None = None,
        middlewares: Sequence[Middleware] = (),
        lifespan: Lifespan | None = None,
    ) -> None:
        self.main_router = main_router
        self.err_handler = err_handler or ErrorHandler()
        self.middlewares = middlewares
        self.lifespan: Lifespan = lifespan or _noop_lifespan


class _HS_Server:
    __slots__ = (
        "_call_next",
        "_lifespan",
        "_routes",
    )

    def __init__(self, app_: HeavySwag) -> None:
        self._routes = CompressedRadixTree(main_router=app_.main_router)
        self._lifespan = partial(app_.lifespan, app_)
        self._call_next = build_middlewares(
            self._assemble_middlewares(app_.err_handler, app_.middlewares),
            self._dispatch,
        )

    def _assemble_middlewares(
        self,
        err_handler: ErrorHandler,
        middlewares: Sequence[Middleware],
    ) -> list[Middleware]:
        assembled: list[Middleware] = []

        if not any(isinstance(m, CORSMiddleware) for m in middlewares):
            assembled.append(CORSMiddleware())

        if not any(
            isinstance(m, ErrorHandlingMiddleware) for m in middlewares
        ):
            assembled.append(ErrorHandlingMiddleware(err_handler))

        if not any(isinstance(m, LoggingMiddleware) for m in middlewares):
            assembled.append(LoggingMiddleware())

        assembled.extend(middlewares)
        return assembled

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] == "http":
            await self._handle_http(scope, receive, send)
            return

        if scope["type"] == "lifespan":
            await self._handle_lifespan(receive, send)
            return

    async def _handle_lifespan(
        self,
        receive: Receive,
        send: Send,
    ) -> None:
        context_manager = self._lifespan()

        message = await receive()
        assert message["type"] == "lifespan.startup"

        try:
            await context_manager.__aenter__()
        except Exception as exc:  # noqa: BLE001
            await send(
                {"type": "lifespan.startup.failed", "message": str(exc)}
            )
            return

        await send({"type": "lifespan.startup.complete"})

        message = await receive()
        assert message["type"] == "lifespan.shutdown"

        try:
            await context_manager.__aexit__(None, None, None)
        except Exception as exc:  # noqa: BLE001
            await send(
                {"type": "lifespan.shutdown.failed", "message": str(exc)}
            )
            return

        await send({"type": "lifespan.shutdown.complete"})

    async def _handle_http(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        serializer = Serializer(_reconstruct_head(scope))

        try:
            context = self._build_context(serializer)
        except KeyError:
            await self._send_response(
                send, serializer, self._bad_method_response()
            )
            return

        await self._load_body(serializer, receive)

        response = await self._call_next(context)
        await self._send_response(send, serializer, response)

    async def _load_body(
        self,
        serializer: Serializer,
        receive: Receive,
    ) -> None:
        more_body = True
        while more_body:
            message = await receive()
            serializer.append_body(message.get("body", b""))
            more_body = message.get("more_body", False)

    def _build_context(self, serializer: Serializer) -> RequestContext:
        preambule = serializer.serialize_preambule()
        request = serializer.serialize_request()

        return RequestContext(
            preambule=preambule,
            request=request,
            serializer=serializer,
        )

    async def _dispatch(self, context: RequestContext) -> Response[Any]:
        if not isinstance(context.preambule.method, HttpMethod):
            return self._not_found_response()

        matched = self._routes.search(
            context.preambule.method, context.preambule.url
        )
        if matched is None:
            return self._not_found_response()

        controller = matched.route.controller
        dto_type = _dto_type(controller)
        query_params = context.serializer.parse_query(
            context.preambule.query
        )
        dto = context.serializer.serialize_dto(
            dto_type, matched.params, query_params
        )

        result = await controller(context.request, dto)

        return context.serializer.wrap_response(result)

    async def _send_response(
        self,
        send: Send,
        serializer: Serializer,
        response: Response[Any],
    ) -> None:
        headers, body = serializer.render(response)

        await send(
            {
                "type": "http.response.start",
                "status": response.status_code,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})

    def _not_found_response(self) -> Response[str]:
        response: Response[str] = Response(status_code=404)
        response.set_body("Not Found")
        return response

    def _bad_method_response(self) -> Response[str]:
        response: Response[str] = Response(status_code=400)
        response.set_body("Unknown HTTP method")
        return response


def _dto_type(controller: Any) -> type[Any]:  # noqa: ANN401
    """The controller's 2nd parameter type — the `dto` that
    `Serializer.serialize_dto` needs to build (1st is always
    `Request`, supplied directly from the parsed request). Reads
    `__annotations__` order directly instead of `inspect.signature`.
    """
    hints = get_type_hints(controller)
    names = [name for name in hints if name != "return"]
    return hints[names[1]]


def _reconstruct_head(scope: Scope) -> bytes:
    """Rebuild the HTTP/1.1 preambule + header block that
    `Serializer` expects, from the already-parsed ASGI scope, so
    method/url/header/cookie parsing has exactly one implementation.

    `Cookie` is re-capitalized because ASGI mandates lowercase
    header names, while `Serializer` matches that one header name
    case-sensitively (mirroring real HTTP/1.1 wire traffic).

    ASGI keeps the query string separate from `path` (`query_string`,
    raw bytes) — it has to be reattached here, otherwise it never
    reaches `serialize_preambule`'s `"?"` split and every `Query[X]`
    field silently looks empty.
    """
    target = scope["path"]
    query_string = scope.get("query_string", b"")
    if query_string:
        target = f"{target}?{query_string.decode('latin-1')}"

    request_line = f"{scope['method']} {target} HTTP/1.1\r\n"
    lines = [request_line.encode("latin-1")]

    for name, value in scope["headers"]:
        header_name = b"Cookie" if name == b"cookie" else name
        lines.append(header_name + b": " + value + b"\r\n")

    lines.append(b"\r\n")
    return b"".join(lines)


def run_app(app: HeavySwag) -> _HS_Server:
    """Инициализация приложение и запуск"""
    return _HS_Server(app_=app)
