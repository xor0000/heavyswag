import string
from collections.abc import Awaitable, Callable
from typing import Any, Concatenate, NamedTuple, Self

from heavyswag.constants import ALLOWED_TYPES, HttpMethod
from heavyswag.doc.models import DocController, DocRouter
from heavyswag.errors import IncludedRouterError
from heavyswag.specify.request import Request
from heavyswag.specify.response import Response

# What a router prefix segment may be built from. Deliberately wider
# than a Python identifier — a prefix ends up in a URL, not in code, so
# `/user-profile` and `/v1` have to be spellable — but still narrow
# enough to keep a prefix a plain, literal piece of path: no percent
# escapes to normalize, no `{name}` to resolve (see `_validate_prefix`).
_PREFIX_CHARS = frozenset(string.ascii_letters + string.digits + "-_.~")

type Controller[
    InDTO: tuple[ALLOWED_TYPES, ...] | None,
    OutDTO: ALLOWED_TYPES | tuple[ALLOWED_TYPES, ...] | None,
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
    doc: DocController | None = None

    def __eq__(self, other: Self) -> bool:  # type: ignore[override]
        return self.path == other.path and self.method == other.method

    def __hash__(self) -> int:
        return hash(f"{self.method}:{self.path}")


class HeavyRouter:
    __slots__ = ("added_routers", "doc", "prefix", "routes")

    def __init__(self, path: str, doc: DocRouter | None = None) -> None:
        self.prefix = path
        self.doc = doc
        self.routes: set[Route[Any, Any, Any]] = set()
        self.added_routers: set[Self] = set()

    def get[
        In: tuple[ALLOWED_TYPES, ...] | None,
        Out: ALLOWED_TYPES | tuple[ALLOWED_TYPES] | None,
        **P,
    ](
        self,
        path: str,
        doc: DocController | None = None,
    ) -> Callable[  # type: ignore[type-var]
        [Controller[In, Out, P]],
        Controller[In, Out, P],
    ]:
        return self._add_route(path, HttpMethod.GET, doc)

    def post[
        In: tuple[ALLOWED_TYPES, ...] | None,
        Out: ALLOWED_TYPES | tuple[ALLOWED_TYPES] | None,
        **P,
    ](
        self,
        path: str,
        doc: DocController | None = None,
    ) -> Callable[  # type: ignore[type-var]
        [Controller[In, Out, P]],
        Controller[In, Out, P],
    ]:
        return self._add_route(path, HttpMethod.POST, doc)

    def put[
        In: tuple[ALLOWED_TYPES, ...] | None,
        Out: ALLOWED_TYPES | tuple[ALLOWED_TYPES] | None,
        **P,
    ](
        self,
        path: str,
        doc: DocController | None = None,
    ) -> Callable[  # type: ignore[type-var]
        [Controller[In, Out, P]],
        Controller[In, Out, P],
    ]:
        return self._add_route(path, HttpMethod.PUT, doc)

    def patch[
        In: tuple[ALLOWED_TYPES, ...] | None,
        Out: ALLOWED_TYPES | tuple[ALLOWED_TYPES] | None,
        **P,
    ](
        self,
        path: str,
        doc: DocController | None = None,
    ) -> Callable[  # type: ignore[type-var]
        [Controller[In, Out, P]],
        Controller[In, Out, P],
    ]:
        return self._add_route(path, HttpMethod.PATCH, doc)

    def delete[
        In: tuple[ALLOWED_TYPES, ...] | None,
        Out: ALLOWED_TYPES | tuple[ALLOWED_TYPES] | None,
        **P,
    ](
        self,
        path: str,
        doc: DocController | None = None,
    ) -> Callable[  # type: ignore[type-var]
        [Controller[In, Out, P]],
        Controller[In, Out, P],
    ]:
        return self._add_route(path, HttpMethod.DELETE, doc)

    def include_router(self, router: Self) -> None:
        prefix = router.prefix

        if self.prefix == prefix:
            msg = f"Cannot add a router with identical paths.\nRoot path: {self.prefix}, included path: {router.prefix}"
            raise IncludedRouterError(msg)

        if router in self.added_routers:
            msg = "Such a router is already connected"
            raise IncludedRouterError(msg)

        self._validate_prefix(prefix)

        self.added_routers.add(router)

    def _validate_prefix(self, prefix: str) -> None:
        """Check an included router's prefix.

        A prefix may span several segments (`/api/v1`), so it's checked
        segment by segment. What it may *not* be is anything that has to
        be resolved at request time: a `{name}` segment belongs on the
        route path, where the DTO's own path fields are matched against
        it (`CompressedRadixTree._validate_path_params`), not on a
        router shared by many DTOs.
        """
        if prefix == "/":
            msg = (
                "A router with the prefix '/' cannot be included — '/' is "
                "the main router's own prefix."
            )
            raise IncludedRouterError(msg)

        if not prefix.startswith("/"):
            msg = "The path must start with '/'."
            raise IncludedRouterError(msg)

        if prefix.endswith("/"):
            msg = f"Prefix '{prefix}' must not end with a trailing '/'."
            raise IncludedRouterError(msg)

        if "{" in prefix or "}" in prefix:
            msg = (
                f"Prefix '{prefix}' must not declare a path parameter — "
                "put '{name}' segments on the route path instead."
            )
            raise IncludedRouterError(msg)

        for segment in prefix[1:].split("/"):
            if not segment:
                msg = f"Prefix '{prefix}' must not contain empty segments."
                raise IncludedRouterError(msg)

            if not _PREFIX_CHARS.issuperset(segment):
                msg = (
                    f"Invalid segment '{segment}' in prefix '{prefix}'. "
                    "Latin letters, digits, '-', '_', '.' and '~' are "
                    "allowed."
                )
                raise IncludedRouterError(msg)

    def _add_route[
        In: tuple[ALLOWED_TYPES, ...] | None,
        Out: ALLOWED_TYPES | tuple[ALLOWED_TYPES] | None,
        **P,
    ](
        self,
        path: str,
        method: HttpMethod,
        doc: DocController | None,
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
                    doc=doc,
                )
            )
            return controller

        return wrapper

    def __eq__(self, other: Self) -> bool:  # type: ignore[override]
        return self.prefix == other.prefix

    def __hash__(self) -> int:
        return hash(self.prefix)
