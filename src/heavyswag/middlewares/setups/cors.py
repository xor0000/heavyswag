from typing import NamedTuple, Callable, Awaitable, Any, Sequence

from heavyswag.constants import MethodType
from heavyswag.specify.response import Response
from heavyswag.middlewares.base import RequestContext, CallNext

class CORSMiddleware:
    __slots__ = (
        "_allow_all",
        "_allow_credentials",
        "_allow_headers",
        "_allow_methods",
        "_allowed_origins",
        "_max_age",
    )

    def __init__(
        self,
        *,
        allow_origins: Sequence[str] = (),
        allow_methods: Sequence[str] = ("GET",),
        allow_headers: Sequence[str] = (),
        allow_credentials: bool = False,
        max_age: int = 600,
    ) -> None:
        self._allow_all = "*" in allow_origins
        self._allow_credentials = allow_credentials
        self._allowed_origins = frozenset(allow_origins)
        self._allow_methods = ", ".join(allow_methods)
        self._allow_headers = ", ".join(allow_headers)
        self._max_age = str(max_age)

    async def __call__(
        self,
        call_next: CallNext,
        context: RequestContext,
    ) -> Response[Any]:
        origin = context.request.headers.get("origin")

        if origin is None or not self._origin_allowed(origin):
            return await call_next(context)

        if self._is_preflight(context):
            return self._preflight_response(origin)

        response = await call_next(context)
        response.attach_header(
            "Access-Control-Allow-Origin",
            self._allow_origin_value(origin),
        )
        response.attach_header("Vary", "Origin")
        if self._allow_credentials:
            response.attach_header(
                "Access-Control-Allow-Credentials", "true"
            )

        return response

    def _origin_allowed(self, origin: str) -> bool:
        return self._allow_all or origin in self._allowed_origins

    def _allow_origin_value(self, origin: str) -> str:
        if self._allow_all and not self._allow_credentials:
            return "*"

        return origin

    def _preflight_response(self, origin: str) -> Response[None]:
        response: Response[None] = Response(status_code=204)
        response.attach_header(
            "Access-Control-Allow-Origin",
            self._allow_origin_value(origin),
        )
        response.attach_header(
            "Access-Control-Allow-Methods", self._allow_methods
        )
        response.attach_header("Access-Control-Max-Age", self._max_age)
        response.attach_header("Vary", "Origin")
        if self._allow_headers:
            response.attach_header(
                "Access-Control-Allow-Headers", self._allow_headers
            )
        if self._allow_credentials:
            response.attach_header(
                "Access-Control-Allow-Credentials", "true"
            )

        return response

    def _is_preflight(self, context: RequestContext) -> bool:
        return (
            context.preambule.method is MethodType.OPTIONS
            and "access-control-request-method" in context.request.headers
        )
