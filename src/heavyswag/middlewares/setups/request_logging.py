from logging import Logger, getLogger
from time import perf_counter
from typing import Any

from heavyswag.middlewares.base import CallNext, RequestContext
from heavyswag.specify.response import Response


class LoggingMiddleware:
    __slots__ = ("_logger",)

    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger or getLogger("heavyswag")

    async def __call__(
        self,
        call_next: CallNext,
        context: RequestContext,
    ) -> Response[Any]:
        started_at = perf_counter()
        status = 500

        try:
            response = await call_next(context)
            status = response.status_code
        finally:
            elapsed_ms = (perf_counter() - started_at) * 1000
            self._logger.info(
                "%s %s -> %d (%.2f ms)",
                context.preambule.method.name,
                context.preambule.url,
                status,
                elapsed_ms,
            )

        return response
