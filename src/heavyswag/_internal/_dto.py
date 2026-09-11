from types import UnionType
from typing import (
    Annotated,
    Any,
    NamedTuple,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from heavyswag.errors import RouteTreeError
from heavyswag.specify.request import BodyMarker, QueryMarker

_NoneType = type(None)

# Before 3.14, `str | None` and `Optional[str]` are two distinct
# objects: `get_origin` reports `types.UnionType` for the first and
# `typing.Union` for the second. 3.14 merged them (`types.UnionType
# is typing.Union`), so this set collapses to a single member there.
_UNION_ORIGINS = frozenset({Union, UnionType})


class DTOField(NamedTuple):
    name: str
    target: Any
    metadata: tuple[Any, ...]
    optional: bool


def resolve_dto_fields(dto_type: type) -> list[DTOField]:
    """Break a DTO's type hints into what `Serializer.serialize_dto`
    and `validate_dto_type` both need: the wire marker(s), the
    underlying scalar type with `Optional` unwrapped, and whether
    `None` is a legal value for the field.
    """
    hints = get_type_hints(dto_type, include_extras=True)
    fields: list[DTOField] = []

    for name, raw_hint in hints.items():
        hint = raw_hint
        optional = False

        if get_origin(hint) in _UNION_ORIGINS:
            args = get_args(hint)
            non_none = tuple(arg for arg in args if arg is not _NoneType)
            if len(non_none) == 1 and len(args) == 2:  # noqa: PLR2004
                optional = True
                hint = non_none[0]

        if get_origin(hint) is Annotated:
            target, *metadata = get_args(hint)
        else:
            target, metadata = hint, []

        fields.append(DTOField(name, target, tuple(metadata), optional))

    return fields


def validate_dto_type(dto_type: type) -> None:
    """Reject DTO shapes the router can't safely serve.

    A `NamedTuple` default would let a field silently fall back
    without the client ever sending it, bypassing the explicit-null
    wire contract `Optional` fields rely on. And a path parameter
    has no way to be 'absent' from a matched URL, so `Optional`
    only makes sense for `Body`/`Query` fields.
    """
    defaults = getattr(dto_type, "_field_defaults", None)
    if defaults:
        names = ", ".join(defaults)
        msg = (
            f"DTO '{dto_type.__name__}' must not declare default values "
            f"for: {names}."
        )
        raise RouteTreeError(msg)

    for field in resolve_dto_fields(dto_type):
        if not field.optional:
            continue

        is_body_or_query = any(
            isinstance(item, BodyMarker | QueryMarker)
            for item in field.metadata
        )
        if not is_body_or_query:
            msg = (
                f"DTO '{dto_type.__name__}' field '{field.name}' is a path "
                "parameter and must not be Optional."
            )
            raise RouteTreeError(msg)


def dto_type(controller: Any) -> type[Any]:  # noqa: ANN401
    """The controller's 2nd parameter type — the `dto` that
    `Serializer.serialize_dto` needs to build (1st is always
    `Request`, supplied directly from the parsed request). Reads
    `__annotations__` order directly instead of `inspect.signature`.
    """
    hints = get_type_hints(controller)
    names = [name for name in hints if name != "return"]
    return hints[names[1]]  # type: ignore[no-any-return]
