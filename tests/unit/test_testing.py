from typing import NamedTuple

import pytest
from httpx import AsyncClient

from heavyswag import HeavyRouter, HeavySwag, run_test
from heavyswag.specify.request import Request


class _Empty(NamedTuple):
    pass


def _build_app() -> HeavySwag:
    router = HeavyRouter("/")

    @router.get("/")
    async def index(_: Request, __: _Empty) -> str:
        return "ok"

    return HeavySwag(main_router=router)


@pytest.mark.asyncio
async def test_run_test_dispatches_requests_to_the_app() -> None:
    client = run_test(_build_app())

    response = await client.get("/")

    assert response.status_code == 200  # noqa: PLR2004
    assert response.text == "ok"


@pytest.mark.asyncio
async def test_run_test_returns_an_async_client() -> None:
    client = run_test(_build_app())

    assert isinstance(client, AsyncClient)


@pytest.mark.asyncio
async def test_run_test_uses_the_given_base_url() -> None:
    client = run_test(_build_app(), base_url="http://custom.example")

    assert str(client.base_url) == "http://custom.example"


@pytest.mark.asyncio
async def test_run_test_defaults_base_url_to_test() -> None:
    client = run_test(_build_app())

    assert str(client.base_url) == "http://test"
