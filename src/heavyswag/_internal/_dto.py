from datetime import datetime
from types import UnionType
from typing import (
    Annotated,
    Any,
    NamedTuple,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)
from uuid import UUID

from heavyswag.errors import RouteTreeError
from heavyswag.specify.request import BodyMarker, QueryMarker
from heavyswag.specify.response import Response

_NoneType = type(None)

# Before 3.14, `str | None` and `Optional[str]` are two distinct
# objects: `get_origin` reports `types.UnionType` for the first and
# `typing.Union` for the second. 3.14 merged them (`types.UnionType
# is typing.Union`), so this set collapses to a single member there.
_UNION_ORIGINS = frozenset({Union, UnionType})

# The non-NamedTuple leaves `Serializer._coerce` knows how to build
# directly from a JSON/query/path scalar. Anything else reaching a
# `Body[...]` field as a plain class (not a generic like `list[X]`)
# has to be a `NamedTuple` instead — there's no other way to
# represent a structured value.
_SCALAR_TYPES = frozenset({int, float, str, bool, bytes, UUID, datetime})


def is_namedtuple(target: Any) -> bool:  # noqa: ANN401
    return (
        isinstance(target, type)
        and issubclass(target, tuple)
        and hasattr(target, "_fields")
    )


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


def _has_no_query_fields(dto_type: type) -> bool:
    """Whether nothing in `dto_type`, recursively, is `Query[...]` —
    the shape a `NamedTuple` must have to be legal as a
    `Body[NamedTuple]` field's target, since there's no query string
    inside a JSON object to resolve a `Query[...]` field from. A bare
    field and a `Body[...]` field are both fine — a bare field there
    is just read straight off the nested JSON object, same as it
    would be off the top-level one, which is also why the very same
    `NamedTuple` can double as a marker-free response DTO (see
    `validate_output_dto_type`). Checked all the way down: a field
    that's itself a `NamedTuple` must be query-free too.
    """
    for field in resolve_dto_fields(dto_type):
        is_query = any(
            isinstance(item, QueryMarker) for item in field.metadata
        )
        if is_query or isinstance(field.target, TypeVar):
            return False

        if is_namedtuple(field.target) and not _has_no_query_fields(
            field.target
        ):
            return False

    return True


def _validate_field_shape(
    dto_type: type,
    field: DTOField,
    *,
    is_body: bool,
    is_query: bool,
) -> None:
    target = field.target

    if isinstance(target, TypeVar):
        # `Body`/`Query` used bare, without `[X]` — the field's
        # target is then the marker's own unbound TypeVar, not a
        # type `Serializer._coerce` could ever build a value from.
        marker_name = "Body" if is_body else "Query"
        msg = (
            f"DTO '{dto_type.__name__}' field '{field.name}' uses "
            f"'{marker_name}' without a type parameter — write "
            f"'{marker_name}[X]' instead."
        )
        raise RouteTreeError(msg)

    if not (isinstance(target, type) and get_origin(target) is None):
        return

    if is_namedtuple(target):
        if is_query:
            msg = (
                f"DTO '{dto_type.__name__}' field '{field.name}' is a "
                "query parameter and must not be a NamedTuple."
            )
            raise RouteTreeError(msg)

        if not is_body:
            msg = (
                f"DTO '{dto_type.__name__}' field '{field.name}' is a "
                "path parameter and must not be a NamedTuple."
            )
            raise RouteTreeError(msg)

        if not _has_no_query_fields(target):
            msg = (
                f"DTO '{dto_type.__name__}' field '{field.name}' nests "
                f"'{target.__name__}', which must not use Query fields "
                "— there's no query string inside a JSON body. A bare "
                "field or Body[X] are both fine."
            )
            raise RouteTreeError(msg)

        return

    if is_body and target not in _SCALAR_TYPES:
        msg = (
            f"DTO '{dto_type.__name__}' field '{field.name}' nests "
            f"'{target.__name__}', which must be a NamedTuple."
        )
        raise RouteTreeError(msg)


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
        is_body = any(isinstance(item, BodyMarker) for item in field.metadata)
        is_query = any(
            isinstance(item, QueryMarker) for item in field.metadata
        )

        if field.optional and not (is_body or is_query):
            msg = (
                f"DTO '{dto_type.__name__}' field '{field.name}' is a path "
                "parameter and must not be Optional."
            )
            raise RouteTreeError(msg)

        _validate_field_shape(
            dto_type, field, is_body=is_body, is_query=is_query
        )


def validate_output_dto_type(dto_type: type) -> None:
    """Reject a response DTO that carries a `Query` marker.

    A response DTO is always serialized whole into the body, so a
    bare field and a `Body[...]` field are equally fine — both just
    end up as a key in the response object. That's also what lets the
    very same `NamedTuple` double as a nested `Body[NamedTuple]`
    target on the way in (see `_has_no_query_fields`) without needing
    a separate, marker-free copy: reusing a request DTO as a nested
    response DTO is not the recommended shape, but it's a valid one.
    `Query`, on the other hand, can never be honored — there's no
    query string to resolve it from on the way out. Checked all the
    way down: a field that's itself a `NamedTuple` is part of the
    same body.
    """
    for field in resolve_dto_fields(dto_type):
        is_query = any(
            isinstance(item, QueryMarker) for item in field.metadata
        )
        if is_query:
            msg = (
                f"DTO '{dto_type.__name__}' field '{field.name}' has a "
                "Query marker, but a response has no query string to "
                "resolve it from — use a bare field or Body[X] instead."
            )
            raise RouteTreeError(msg)

        if is_namedtuple(field.target):
            validate_output_dto_type(field.target)


def dto_path_param_names(dto_type: type) -> frozenset[str]:
    """The DTO fields that resolve from a path segment — anything
    with neither a `Body` nor a `Query` marker. `CompressedRadixTree`
    compares this against the route's own `{name}` segments, so a
    mismatch is caught at startup instead of surfacing as a
    per-request 'Missing field' `SerializationError`.
    """
    names = set()

    for field in resolve_dto_fields(dto_type):
        is_body = any(isinstance(item, BodyMarker) for item in field.metadata)
        is_query = any(
            isinstance(item, QueryMarker) for item in field.metadata
        )
        if not is_body and not is_query:
            names.add(field.name)

    return frozenset(names)


def dto_type(controller: Any) -> type[Any]:  # noqa: ANN401
    """The controller's 2nd parameter type — the `dto` that
    `Serializer.serialize_dto` needs to build (1st is always
    `Request`, supplied directly from the parsed request). Reads
    `__annotations__` order directly instead of `inspect.signature`.
    """
    hints = get_type_hints(controller)
    names = [name for name in hints if name != "return"]
    return hints[names[1]]  # type: ignore[no-any-return]


def output_dto_type(controller: Any) -> Any:  # noqa: ANN401
    """The controller's return type, with `Response[...]` unwrapped
    to the DTO it carries — a bare `NamedTuple` return and a
    `Response[NamedTuple]` return end up in the same body, so
    `validate_output_dto_type` needs the same target either way.
    """
    return_type = get_type_hints(controller)["return"]

    if get_origin(return_type) is Response:
        (return_type,) = get_args(return_type)

    return return_type
