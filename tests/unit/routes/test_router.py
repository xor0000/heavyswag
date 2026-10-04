import pytest

from heavyswag.errors import IncludedRouterError
from heavyswag.routes.router import HeavyRouter
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


@pytest.mark.parametrize(
    "prefix",
    [
        "/users",
        "/api/v1",
        "/api/v1/internal",
        "/v1",
        "/user-profile",
        "/user_profile",
        "/v2.1",
        "/v2~beta",
    ],
)
def test_include_router_accepts_prefix(prefix: str) -> None:
    """A prefix is a literal piece of URL path, so it may span several
    segments and use any of the URL-safe characters a path segment
    normally carries — not just letters.
    """
    main_router = HeavyRouter("/")

    main_router.include_router(HeavyRouter(prefix))

    assert HeavyRouter(prefix) in main_router.added_routers


@pytest.mark.parametrize(
    "prefix",
    [
        "users",
        "/users/",
        "/api/v1/",
        "/api//v1",
        "/api/{version}",
        "/прив",
        "/with space",
        "/a%20b",
        "/a?b",
        "/a#b",
    ],
)
def test_include_router_rejects_prefix(prefix: str) -> None:
    main_router = HeavyRouter("/")

    with pytest.raises(IncludedRouterError):
        main_router.include_router(HeavyRouter(prefix))


def test_include_root_router_into_a_sub_router() -> None:
    """`/` is the main router's own prefix — including a second router
    that claims it would put two routers at the same place in the tree.
    """
    users_router = HeavyRouter("/users")

    with pytest.raises(IncludedRouterError, match="main router"):
        users_router.include_router(HeavyRouter("/"))
