import pytest

from heavyswag.constants import HttpMethod
from heavyswag.errors import RouteTreeError
from heavyswag.routes.radix_tree import CompressedRadixTree
from heavyswag.routes.router import HeavyRouter
from heavyswag.specify.request import Request


async def _controller(_: Request, __: tuple[()]) -> None:
    return None


async def _other_controller(_: Request, __: tuple[()]) -> None:
    return None


def test_main_router_must_be_root() -> None:
    with pytest.raises(RouteTreeError):
        CompressedRadixTree(HeavyRouter("/sub"))


def test_search_static_and_nested_routes() -> None:
    main_router = HeavyRouter("/")
    users_router = HeavyRouter("/users")
    account_router = HeavyRouter("/account")

    main_router.get("/doc")(_controller)
    users_router.get("/")(_controller)
    users_router.get("/{user_id}")(_controller)
    users_router.get("/{user_id}/profile")(_controller)
    users_router.post("/")(_other_controller)
    account_router.get("/profile")(_controller)
    account_router.patch("/profile")(_other_controller)

    main_router.include_router(users_router)
    main_router.include_router(account_router)

    tree = CompressedRadixTree(main_router)

    doc = tree.search(HttpMethod.GET, "/doc")
    assert doc is not None
    assert doc.params == {}

    users = tree.search(HttpMethod.GET, "/users")
    assert users is not None
    assert users.params == {}

    user = tree.search(HttpMethod.GET, "/users/42")
    assert user is not None
    assert user.route.path == "/{user_id}"
    assert user.params == {"user_id": "42"}

    profile = tree.search(HttpMethod.GET, "/users/42/profile")
    assert profile is not None
    assert profile.params == {"user_id": "42"}

    created = tree.search(HttpMethod.POST, "/users")
    assert created is not None
    assert created.route.controller is _other_controller

    account = tree.search(HttpMethod.GET, "/account/profile")
    assert account is not None
    assert account.route.controller is _controller

    updated_account = tree.search(HttpMethod.PATCH, "/account/profile")
    assert updated_account is not None
    assert updated_account.route.controller is _other_controller


def test_search_unknown_path_returns_none() -> None:
    main_router = HeavyRouter("/")
    main_router.get("/doc")(_controller)

    tree = CompressedRadixTree(main_router)

    assert tree.search(HttpMethod.GET, "/unknown") is None


def test_search_unregistered_method_returns_none() -> None:
    main_router = HeavyRouter("/")
    main_router.get("/doc")(_controller)

    tree = CompressedRadixTree(main_router)

    assert tree.search(HttpMethod.DELETE, "/doc") is None


def test_search_root_route() -> None:
    main_router = HeavyRouter("/")
    main_router.get("/")(_controller)

    tree = CompressedRadixTree(main_router)

    root = tree.search(HttpMethod.GET, "/")
    assert root is not None
    assert root.params == {}


def test_static_route_has_priority_over_param_route() -> None:
    main_router = HeavyRouter("/")
    main_router.get("/items/act")(_controller)
    main_router.get("/items/{item_id}")(_other_controller)

    tree = CompressedRadixTree(main_router)

    static_match = tree.search(HttpMethod.GET, "/items/act")
    assert static_match is not None
    assert static_match.route.controller is _controller
    assert static_match.params == {}

    param_match = tree.search(HttpMethod.GET, "/items/action")
    assert param_match is not None
    assert param_match.route.controller is _other_controller
    assert param_match.params == {"item_id": "action"}

    short_match = tree.search(HttpMethod.GET, "/items/ac")
    assert short_match is not None
    assert short_match.route.controller is _other_controller
    assert short_match.params == {"item_id": "ac"}


def test_empty_param_value_does_not_match() -> None:
    main_router = HeavyRouter("/")
    main_router.get("/x/{item_id}/y")(_controller)

    tree = CompressedRadixTree(main_router)

    assert tree.search(HttpMethod.GET, "/x//y") is None


def test_param_backtrack_is_undone_on_deeper_mismatch() -> None:
    main_router = HeavyRouter("/")
    main_router.get("/items/{item_id}/extra")(_controller)

    tree = CompressedRadixTree(main_router)

    assert tree.search(HttpMethod.GET, "/items/42") is None
    assert tree.search(HttpMethod.GET, "/items/42/extra") is not None


def test_shared_prefix_compression() -> None:
    main_router = HeavyRouter("/")
    main_router.get("/team")(_controller)
    main_router.get("/teams")(_other_controller)
    main_router.get("/test")(_controller)

    tree = CompressedRadixTree(main_router)

    team = tree.search(HttpMethod.GET, "/team")
    assert team is not None
    assert team.route.controller is _controller

    teams = tree.search(HttpMethod.GET, "/teams")
    assert teams is not None
    assert teams.route.controller is _other_controller

    test = tree.search(HttpMethod.GET, "/test")
    assert test is not None
    assert test.route.controller is _controller

    assert tree.search(HttpMethod.GET, "/te") is None
    assert tree.search(HttpMethod.GET, "/tea") is None


def test_duplicate_route_raises() -> None:
    main_router = HeavyRouter("/")
    main_router.get("/x")(_controller)

    sub_router = HeavyRouter("/x")
    sub_router.get("/")(_other_controller)
    main_router.include_router(sub_router)

    with pytest.raises(RouteTreeError):
        CompressedRadixTree(main_router)


def test_conflicting_param_name_raises() -> None:
    main_router = HeavyRouter("/")
    main_router.get("/items/{item_id}")(_controller)

    sub_router = HeavyRouter("/items")
    sub_router.get("/{id}")(_other_controller)
    main_router.include_router(sub_router)

    with pytest.raises(RouteTreeError):
        CompressedRadixTree(main_router)


def test_circular_router_inclusion_raises() -> None:
    router_a = HeavyRouter("/a")
    router_b = HeavyRouter("/b")
    router_a.include_router(router_b)
    router_b.include_router(router_a)

    main_router = HeavyRouter("/")
    main_router.include_router(router_a)

    with pytest.raises(RouteTreeError):
        CompressedRadixTree(main_router)


def test_invalid_paths_raise() -> None:
    missing_slash = HeavyRouter("/")
    missing_slash.get("relative")(_controller)
    with pytest.raises(RouteTreeError):
        CompressedRadixTree(missing_slash)

    trailing_slash = HeavyRouter("/")
    trailing_slash.get("/foo/")(_controller)
    with pytest.raises(RouteTreeError):
        CompressedRadixTree(trailing_slash)

    double_slash = HeavyRouter("/")
    double_slash.get("//foo")(_controller)
    with pytest.raises(RouteTreeError):
        CompressedRadixTree(double_slash)

    partial_param = HeavyRouter("/")
    partial_param.get("/foo{id}")(_controller)
    with pytest.raises(RouteTreeError):
        CompressedRadixTree(partial_param)


def test_invalid_path_parameters_raise() -> None:
    empty_name = HeavyRouter("/")
    empty_name.get("/{}")(_controller)
    with pytest.raises(RouteTreeError):
        CompressedRadixTree(empty_name)

    starts_with_digit = HeavyRouter("/")
    starts_with_digit.get("/{1abc}")(_controller)
    with pytest.raises(RouteTreeError):
        CompressedRadixTree(starts_with_digit)

    invalid_char = HeavyRouter("/")
    invalid_char.get("/{ab-cd}")(_controller)
    with pytest.raises(RouteTreeError):
        CompressedRadixTree(invalid_char)

    duplicate_name = HeavyRouter("/")
    duplicate_name.get("/{id}/sub/{id}")(_controller)
    with pytest.raises(RouteTreeError):
        CompressedRadixTree(duplicate_name)
