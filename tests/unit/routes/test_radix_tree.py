from typing import NamedTuple

import pytest

from heavyswag.constants import HttpMethod
from heavyswag.errors import RouteTreeError
from heavyswag.routes.radix_tree import CompressedRadixTree
from heavyswag.routes.router import HeavyRouter
from heavyswag.specify.request import Body, Query, Request
from heavyswag.specify.response import Response


class _Empty(NamedTuple):
    pass


class _UserId(NamedTuple):
    user_id: str


class _ItemId(NamedTuple):
    item_id: str


class _Id(NamedTuple):
    id: str


async def _controller(_: Request, __: _Empty) -> None:
    return None


async def _other_controller(_: Request, __: _Empty) -> None:
    return None


async def _user_controller(_: Request, __: _UserId) -> None:
    return None


async def _item_controller(_: Request, __: _ItemId) -> None:
    return None


async def _id_controller(_: Request, __: _Id) -> None:
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
    users_router.get("/{user_id}")(_user_controller)
    users_router.get("/{user_id}/profile")(_user_controller)
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
    main_router.get("/items/{item_id}")(_item_controller)

    tree = CompressedRadixTree(main_router)

    static_match = tree.search(HttpMethod.GET, "/items/act")
    assert static_match is not None
    assert static_match.route.controller is _controller
    assert static_match.params == {}

    param_match = tree.search(HttpMethod.GET, "/items/action")
    assert param_match is not None
    assert param_match.route.controller is _item_controller
    assert param_match.params == {"item_id": "action"}

    short_match = tree.search(HttpMethod.GET, "/items/ac")
    assert short_match is not None
    assert short_match.route.controller is _item_controller
    assert short_match.params == {"item_id": "ac"}


def test_empty_param_value_does_not_match() -> None:
    main_router = HeavyRouter("/")
    main_router.get("/x/{item_id}/y")(_item_controller)

    tree = CompressedRadixTree(main_router)

    assert tree.search(HttpMethod.GET, "/x//y") is None


def test_param_backtrack_is_undone_on_deeper_mismatch() -> None:
    main_router = HeavyRouter("/")
    main_router.get("/items/{item_id}/extra")(_item_controller)

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
    main_router.get("/items/{item_id}")(_item_controller)

    sub_router = HeavyRouter("/items")
    sub_router.get("/{id}")(_id_controller)
    main_router.include_router(sub_router)

    with pytest.raises(RouteTreeError, match="Conflicting path parameter"):
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


def test_dto_with_default_value_raises() -> None:
    class _WithDefault(NamedTuple):
        value: Body[str] | None = None

    async def controller(_: Request, __: _WithDefault) -> None:
        return None

    router = HeavyRouter("/")
    router.get("/x")(controller)

    with pytest.raises(
        RouteTreeError, match="must not declare default values"
    ):
        CompressedRadixTree(router)


def test_dto_optional_path_param_raises() -> None:
    class _OptionalPath(NamedTuple):
        item_id: str | None

    async def controller(_: Request, __: _OptionalPath) -> None:
        return None

    router = HeavyRouter("/")
    router.get("/{item_id}")(controller)

    with pytest.raises(RouteTreeError, match="must not be Optional"):
        CompressedRadixTree(router)


def test_dto_optional_body_and_query_are_allowed() -> None:
    class _Optional(NamedTuple):
        value1: Body[str] | None
        value2: Query[str] | None
        value3: str

    async def controller(_: Request, __: _Optional) -> None:
        return None

    router = HeavyRouter("/")
    router.get("/{value3}")(controller)

    tree = CompressedRadixTree(router)

    matched = tree.search(HttpMethod.GET, "/abc")
    assert matched is not None


def test_dto_path_param_missing_from_route_raises() -> None:
    """A DTO's path (bare) field has to come from *somewhere* in the
    URL — declaring one with no matching `{name}` segment used to
    only surface per-request, as a confusing 'Missing field'
    `SerializationError`. It's now caught once, at startup.
    """

    class _DTO(NamedTuple):
        value: str

    async def controller(_: Request, __: _DTO) -> None:
        return None

    router = HeavyRouter("/")
    router.post("/")(controller)

    with pytest.raises(
        RouteTreeError, match=r"field 'value' is a path parameter"
    ):
        CompressedRadixTree(router)


def test_route_path_param_missing_from_dto_raises() -> None:
    """The reverse mismatch: a `{name}` segment in the route that no
    DTO field ever resolves — the value would just be silently
    discarded, so it's caught the same way.
    """

    router = HeavyRouter("/")
    router.post("/{value}")(_controller)

    with pytest.raises(
        RouteTreeError, match=r"declares path parameter '\{value\}'"
    ):
        CompressedRadixTree(router)


def test_dto_path_param_matching_route_is_allowed() -> None:
    class _DTO(NamedTuple):
        value: str

    async def controller(_: Request, __: _DTO) -> None:
        return None

    router = HeavyRouter("/")
    router.post("/{value}")(controller)

    tree = CompressedRadixTree(router)

    assert tree.search(HttpMethod.POST, "/anything") is not None


def test_output_dto_with_body_marker_is_allowed() -> None:
    """A `Body[...]` marker on an output field is redundant but
    harmless — allowing it is what lets a request DTO double as a
    nested response DTO without a separate, marker-free copy.
    """

    class _Out(NamedTuple):
        value: Body[str]

    async def controller(_: Request, __: _Empty) -> _Out:
        return _Out(value="x")

    router = HeavyRouter("/")
    router.get("/x")(controller)

    tree = CompressedRadixTree(router)

    assert tree.search(HttpMethod.GET, "/x") is not None


def test_output_dto_with_query_marker_wrapped_in_response_raises() -> None:
    class _Out(NamedTuple):
        value: Query[str]

    async def controller(_: Request, __: _Empty) -> Response[_Out]:
        return Response()

    router = HeavyRouter("/")
    router.get("/x")(controller)

    with pytest.raises(RouteTreeError, match="Query marker"):
        CompressedRadixTree(router)


def test_output_dto_with_query_marker_in_nested_bare_field_raises() -> None:
    """A marker doesn't have to sit on the outer field to be invalid
    — `details` itself is bare, but its target `_Details` carries a
    `Query[...]` field, and that's still part of the same response
    body once it's nested.
    """

    class _Details(NamedTuple):
        value: Query[str]

    class _Out(NamedTuple):
        id: str
        details: _Details

    async def controller(_: Request, __: _Empty) -> _Out:
        return _Out(id="1", details=_Details(value="x"))

    router = HeavyRouter("/")
    router.get("/x")(controller)

    with pytest.raises(RouteTreeError, match="Query marker"):
        CompressedRadixTree(router)


def test_output_dto_without_markers_is_allowed() -> None:
    class _Out(NamedTuple):
        id: str
        name: str

    async def controller(_: Request, __: _Empty) -> _Out:
        return _Out(id="1", name="x")

    router = HeavyRouter("/")
    router.get("/x")(controller)

    tree = CompressedRadixTree(router)

    assert tree.search(HttpMethod.GET, "/x") is not None


def test_output_dto_with_pure_nested_namedtuple_is_allowed() -> None:
    """The mirror image of the marker test above: a nested, bare
    `NamedTuple` field with no markers anywhere is a perfectly normal
    response shape and must not be rejected.
    """

    class _Details(NamedTuple):
        value1: str
        value2: str

    class _Out(NamedTuple):
        id: str
        details: _Details

    async def controller(_: Request, __: _Empty) -> _Out:
        return _Out(id="1", details=_Details(value1="a", value2="b"))

    router = HeavyRouter("/")
    router.get("/x")(controller)

    tree = CompressedRadixTree(router)

    assert tree.search(HttpMethod.GET, "/x") is not None


def test_output_scalar_return_type_is_allowed() -> None:
    async def controller(_: Request, __: _Empty) -> str:
        return "ok"

    router = HeavyRouter("/")
    router.get("/x")(controller)

    tree = CompressedRadixTree(router)

    assert tree.search(HttpMethod.GET, "/x") is not None
