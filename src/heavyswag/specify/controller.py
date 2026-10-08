from collections.abc import Awaitable, Callable
from typing import Concatenate

from heavyswag.constants import ALLOWED_TYPES
from heavyswag.specify.request import Request
from heavyswag.specify.response import Response

# The shape of every route handler: the parsed `Request`, the DTO built
# from the path / query / body, and a DTO (or a `Response` carrying one)
# back. Lives here, next to `Request` and `Response`, rather than in the
# router — so anything that needs to talk about a controller can, without
# depending on `heavyswag.routes`.
type Controller[
    InDTO: tuple[ALLOWED_TYPES, ...] | None,
    OutDTO: ALLOWED_TYPES | tuple[ALLOWED_TYPES, ...] | None,
    **P,
] = Callable[
    Concatenate[Request, InDTO, P], Awaitable[OutDTO | Response[OutDTO]]  # type: ignore[type-var]
]
