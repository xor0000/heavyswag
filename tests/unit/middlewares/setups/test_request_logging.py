import logging

import pytest

from heavyswag._internal._serializer import Serializer
from heavyswag.constants import HttpMethod
from heavyswag.middlewares.base import RequestContext
from heavyswag.middlewares.setups.request_logging import LoggingMiddleware
from heavyswag.specify.request import Preambule, Request
from heavyswag.specify.response import Response


def _context() -> RequestContext:
    return RequestContext(
        preambule=Preambule(url="/hello", method=HttpMethod.GET),
        request=Request(headers=[], cookies=[]),
        serializer=Serializer(b""),
    )


def test_defaults_to_heavyswag_logger() -> None:
    middleware = LoggingMiddleware()

    assert middleware._logger.name == "heavyswag"  # noqa: SLF001


def test_uses_provided_logger_instance() -> None:
    logger = logging.getLogger("custom")

    middleware = LoggingMiddleware(logger)

    assert middleware._logger is logger  # noqa: SLF001


@pytest.mark.asyncio
async def test_logs_successful_response_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    middleware = LoggingMiddleware()

    async def handler(_context: RequestContext) -> Response[str]:
        response: Response[str] = Response(status_code=201)
        response.content = "ok"
        return response

    with caplog.at_level(logging.INFO, logger="heavyswag"):
        response = await middleware(handler, _context())

    assert response.status_code == 201  # noqa: PLR2004
    assert "GET /hello -> 201" in caplog.text


@pytest.mark.asyncio
async def test_logs_default_status_and_reraises_on_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    middleware = LoggingMiddleware()

    async def handler(_context: RequestContext) -> Response[str]:
        msg = "boom"
        raise RuntimeError(msg)

    with (
        caplog.at_level(logging.INFO, logger="heavyswag"),
        pytest.raises(RuntimeError, match="boom"),
    ):
        await middleware(handler, _context())

    assert "GET /hello -> 500" in caplog.text
