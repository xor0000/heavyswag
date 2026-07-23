from collections.abc import Awaitable, Callable
from typing import Any, Concatenate, NamedTuple, Self

from heavyswag.constants import ALLOWED_TYPES, HttpMethod
from heavyswag.errors import IncludedRouterError
from heavyswag.specify.request import Request
from heavyswag.specify.response import Response

type Controller[
    InDTO: tuple[ALLOWED_TYPES, ...] | None,
    OutDTO: tuple[ALLOWED_TYPES, ...] | None,
    **P,
] = Callable[
    Concatenate[Request, InDTO, P], Awaitable[OutDTO | Response[OutDTO]]  # type: ignore[type-var]
]


class Route[
    InDTO: tuple[ALLOWED_TYPES, ...] | None,
    OutDTO: tuple[ALLOWED_TYPES] | None,
    **P,
](NamedTuple):
    method: HttpMethod
    path: str
    controller: Controller[InDTO, OutDTO, P]  # type: ignore[type-var]

    def __eq__(self, other: Self) -> bool:  # type: ignore[override]
        return self.path == other.path and self.method == other.method

    def __hash__(self) -> int:
        return hash(f"{self.method}:{self.path}")


class HeavyRouter:
    __slots__ = ("added_routers", "prefix", "routes")

    def __init__(self, path: str) -> None:
        self.prefix = path
        self.routes: set[Route[Any, Any, Any]] = set()
        self.added_routers: set[Self] = set()

    def get[
        In: tuple[ALLOWED_TYPES, ...] | None,
        Out: tuple[ALLOWED_TYPES] | None,
        **P,
    ](
        self,
        path: str,
    ) -> Callable[  # type: ignore[type-var]
        [Controller[In, Out, P]],
        Controller[In, Out, P],
    ]:
        return self._add_route(path, HttpMethod.GET)

    def post[
        In: tuple[ALLOWED_TYPES, ...] | None,
        Out: tuple[ALLOWED_TYPES] | None,
        **P,
    ](
        self,
        path: str,
    ) -> Callable[  # type: ignore[type-var]
        [Controller[In, Out, P]],
        Controller[In, Out, P],
    ]:
        return self._add_route(path, HttpMethod.POST)

    def put[
        In: tuple[ALLOWED_TYPES, ...] | None,
        Out: tuple[ALLOWED_TYPES] | None,
        **P,
    ](
        self,
        path: str,
    ) -> Callable[  # type: ignore[type-var]
        [Controller[In, Out, P]],
        Controller[In, Out, P],
    ]:
        return self._add_route(path, HttpMethod.PUT)

    def patch[
        In: tuple[ALLOWED_TYPES, ...] | None,
        Out: tuple[ALLOWED_TYPES] | None,
        **P,
    ](
        self,
        path: str,
    ) -> Callable[  # type: ignore[type-var]
        [Controller[In, Out, P]],
        Controller[In, Out, P],
    ]:
        return self._add_route(path, HttpMethod.PATCH)

    def delete[
        In: tuple[ALLOWED_TYPES, ...] | None,
        Out: tuple[ALLOWED_TYPES] | None,
        **P,
    ](
        self,
        path: str,
    ) -> Callable[  # type: ignore[type-var]
        [Controller[In, Out, P]],
        Controller[In, Out, P],
    ]:
        return self._add_route(path, HttpMethod.DELETE)

    def include_router(self, router: Self) -> None:
        prefix = router.prefix

        if self.prefix == prefix:
            msg = f"Cannot add a router with identical paths.\nRoot path: {self.prefix}, included path: {router.prefix}"
            raise IncludedRouterError(msg)

        if prefix[0] != "/":
            msg = "The path must start with '/'."
            raise IncludedRouterError(msg)

        if router in self.added_routers:
            msg = "Such a router is already connected"
            raise IncludedRouterError(msg)

        prefix = prefix[1:]

        if not (prefix.isalpha() and prefix.isascii()):
            msg = "Invalid path. Latin characters are allowed"
            raise IncludedRouterError(msg)

        self.added_routers.add(router)

    def _add_route[
        In: tuple[ALLOWED_TYPES, ...] | None,
        Out: tuple[ALLOWED_TYPES] | None,
        **P,
    ](
        self,
        path: str,
        method: HttpMethod,
    ) -> Callable[  # type: ignore[type-var]
        [Controller[In, Out, P]],
        Controller[In, Out, P],
    ]:
        def wrapper(
            controller: Controller[In, Out, P],  # type: ignore[type-var]
        ) -> Controller[In, Out, P]:  # type: ignore[type-var]
            self.routes.add(
                Route(
                    path=path,
                    method=method,
                    controller=controller,
                )
            )
            return controller

        return wrapper

    def __eq__(self, other: Self) -> bool:  # type: ignore[override]
        return self.prefix == other.prefix

    def __hash__(self) -> int:
        return hash(self.prefix)
