import pytest

from heavyswag.errors import IncludedRouterError
from heavyswag.routes.router import BaseRouteClass, HeavyRouter
from heavyswag.specify.request import Request


def test_added_routes() -> None:
    router = HeavyRouter(path="/")

    @router.get("/")
    async def get_controller(_: Request, __: tuple[()]) -> None:
        return None

    @router.post("/")
    async def post_controller(_: Request, __: tuple[()]) -> None:
        return None

    @router.patch("/")
    async def patch_controller(_: Request, __: tuple[()]) -> None:
        return None

    @router.put("/")
    async def put_controller(_: Request, __: tuple[()]) -> None:
        return None

    @router.delete("/")
    async def delete_controller(_: Request, __: tuple[()]) -> None:
        return None

    @router.delete("/")
    async def delete_controller_duble(_: Request, __: tuple[()]) -> None:
        return None

    @router.delete("/{user_id}")
    async def delete_controller_path_param(_: Request, __: tuple[()]) -> None:
        return None

    assert len(router.routes) == 6  # noqa: PLR2004


def test_added_router() -> None:
    main_router = HeavyRouter("/")

    main_router.include_router(HeavyRouter("/users"))

    with pytest.raises(IncludedRouterError):
        main_router.include_router(HeavyRouter("/"))

    with pytest.raises(IncludedRouterError):
        main_router.include_router(HeavyRouter("/users"))

    with pytest.raises(IncludedRouterError):
        main_router.include_router(HeavyRouter("/users/{user_id}"))

    with pytest.raises(IncludedRouterError):
        main_router.include_router(HeavyRouter("accounts"))


@pytest.mark.asyncio
async def test_route_class() -> None:
    async def controller(_: Request, __: tuple[()]) -> None:
        return None

    req = Request({}, {})

    await BaseRouteClass().handle(req, controller)
