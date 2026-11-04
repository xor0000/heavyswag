import pytest

from heavyswag._internal._serializer import Serializer
from heavyswag.constants import HttpMethod, MethodType
from heavyswag.middlewares.base import RequestContext
from heavyswag.middlewares.setups.cors import CORSMiddleware
from heavyswag.specify.request import Preambule, Request
from heavyswag.specify.response import Response


def _context(
    method: HttpMethod | MethodType = HttpMethod.GET,
    headers: dict[str, str] | None = None,
) -> RequestContext:
    header_items = list(headers.items()) if headers else []
    return RequestContext(
        preambule=Preambule(url="/", method=method),
        request=Request(headers=header_items, cookies=[]),
        serializer=Serializer(b""),
    )


async def _handler(_context: RequestContext) -> Response[str]:
    response: Response[str] = Response(status_code=200)
    response.content = "ok"
    return response


@pytest.mark.asyncio
async def test_no_origin_header_passes_through_untouched() -> None:
    middleware = CORSMiddleware(allow_origins=["https://example.com"])

    response = await middleware(_handler, _context())

    assert response.content == "ok"
    assert response.headers is None


@pytest.mark.asyncio
async def test_disallowed_origin_passes_through_without_headers() -> None:
    middleware = CORSMiddleware(allow_origins=["https://example.com"])
    context = _context(headers={"origin": "https://evil.com"})

    response = await middleware(_handler, context)

    assert response.content == "ok"
    assert response.headers is None


@pytest.mark.asyncio
async def test_allowed_origin_attaches_headers() -> None:
    middleware = CORSMiddleware(allow_origins=["https://example.com"])
    context = _context(headers={"origin": "https://example.com"})

    response = await middleware(_handler, context)

    assert response.headers is not None
    assert (
        "Access-Control-Allow-Origin",
        "https://example.com",
    ) in response.headers
    assert ("Vary", "Origin") in response.headers
    assert not any(
        key == "Access-Control-Allow-Credentials"
        for key, _ in response.headers
    )


@pytest.mark.asyncio
async def test_allowed_origin_with_credentials_attaches_credentials_header() -> (
    None
):
    middleware = CORSMiddleware(
        allow_origins=["https://example.com"],
        allow_credentials=True,
    )
    context = _context(headers={"origin": "https://example.com"})

    response = await middleware(_handler, context)

    assert response.headers is not None
    assert ("Access-Control-Allow-Credentials", "true") in response.headers


@pytest.mark.asyncio
async def test_wildcard_origin_without_credentials_returns_star() -> None:
    middleware = CORSMiddleware(allow_origins=["*"])
    context = _context(headers={"origin": "https://anything.example"})

    response = await middleware(_handler, context)

    assert response.headers is not None
    assert ("Access-Control-Allow-Origin", "*") in response.headers


@pytest.mark.asyncio
async def test_wildcard_origin_with_credentials_echoes_origin() -> None:
    middleware = CORSMiddleware(allow_origins=["*"], allow_credentials=True)
    context = _context(headers={"origin": "https://anything.example"})

    response = await middleware(_handler, context)

    assert response.headers is not None
    assert (
        "Access-Control-Allow-Origin",
        "https://anything.example",
    ) in response.headers


@pytest.mark.asyncio
async def test_preflight_request_returns_204_without_calling_handler() -> None:
    called = False

    async def handler(_context: RequestContext) -> Response[str]:
        nonlocal called
        called = True
        return Response()

    middleware = CORSMiddleware(
        allow_origins=["https://example.com"],
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
        allow_credentials=True,
        max_age=120,
    )
    context = _context(
        method=MethodType.OPTIONS,
        headers={
            "origin": "https://example.com",
            "access-control-request-method": "POST",
        },
    )

    response = await middleware(handler, context)

    assert called is False
    assert response.status_code == 204  # noqa: PLR2004
    assert response.headers is not None
    assert ("Access-Control-Allow-Methods", "GET, POST") in response.headers
    assert ("Access-Control-Max-Age", "120") in response.headers
    assert ("Access-Control-Allow-Headers", "content-type") in response.headers
    assert ("Access-Control-Allow-Credentials", "true") in response.headers


@pytest.mark.asyncio
async def test_preflight_without_allow_headers_or_credentials_omits_them() -> (
    None
):
    middleware = CORSMiddleware(allow_origins=["https://example.com"])
    context = _context(
        method=MethodType.OPTIONS,
        headers={
            "origin": "https://example.com",
            "access-control-request-method": "GET",
        },
    )

    response = await middleware(_handler, context)

    assert response.headers is not None
    keys = {key for key, _ in response.headers}
    assert "Access-Control-Allow-Headers" not in keys
    assert "Access-Control-Allow-Credentials" not in keys


@pytest.mark.asyncio
async def test_options_without_preflight_header_runs_handler() -> None:
    """OPTIONS from an allowed origin but missing the
    Access-Control-Request-Method header is a normal request, not a
    preflight — the handler still runs.
    """
    middleware = CORSMiddleware(allow_origins=["https://example.com"])
    context = _context(
        method=MethodType.OPTIONS,
        headers={"origin": "https://example.com"},
    )

    response = await middleware(_handler, context)

    assert response.content == "ok"
    assert response.status_code == 200  # noqa: PLR2004
