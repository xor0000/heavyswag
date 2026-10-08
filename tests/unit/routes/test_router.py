import pytest

from heavyswag.constants import HttpMethod
from heavyswag.doc import DocController, DocRouter, DocTag
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


def test_route_without_doc() -> None:
    router = HeavyRouter("/")

    @router.get("/")
    async def controller(_: Request, __: tuple[()]) -> None:
        return None

    (route,) = router.routes
    assert route.doc is None


@pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete"])
def test_route_keeps_doc(method: str) -> None:
    router = HeavyRouter("/", doc=DocRouter(tags=[DocTag("Users")]))
    doc = DocController(summary="Create", success_status_code=201)
    # A dict, not `getattr`: the latter is `Any` to mypy, which would make
    # the decorator — and so the controller — untyped under `--strict`.
    register = {
        "get": router.get,
        "post": router.post,
        "put": router.put,
        "patch": router.patch,
        "delete": router.delete,
    }[method]

    @register("/", doc=doc)
    async def controller(_: Request, __: tuple[()]) -> None:
        return None

    (route,) = router.routes
    assert route.method is HttpMethod[method.upper()]
    assert route.doc is doc
    assert router.doc == DocRouter(tags=[DocTag("Users")])
