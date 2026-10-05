import json
from datetime import datetime
from enum import Enum
from typing import Any, Final, get_args, get_origin
from uuid import UUID

from heavyswag._internal._dto import (
    DTOField,
    FieldSource,
    is_enum,
    is_namedtuple,
    resolve_dto_fields,
)
from heavyswag.constants import ALLOWED_TYPES, HttpMethod, MethodType
from heavyswag.errors import SerializationError
from heavyswag.specify.cookie import Cookie
from heavyswag.specify.request import Preambule, Request
from heavyswag.specify.response import Response

CR: Final = ord("\r")
LF: Final = ord("\n")
SP: Final = ord(" ")
DC: Final = ord("=")
SC: Final = ord(";")
CN: Final = ord(":")

METHODS: Final[dict[str, HttpMethod | MethodType]] = {
    **HttpMethod.__members__,
    **MethodType.__members__,
}

_NO_BODY_STATUSES: Final = frozenset({204, 304})

_TEXT_CONTENT_TYPE: Final = b"text/plain; charset=utf-8"
_BINARY_CONTENT_TYPE: Final = b"application/octet-stream"
_JSON_CONTENT_TYPE: Final = b"application/json"


class Serializer:
    def __init__(self, request: bytes) -> None:
        self._request = request
        self._offset = 0

    def append_body(self, chunk: bytes) -> None:
        """Append a body chunk received from ASGI's `receive()`.

        The buffer only ever holds the reconstructed request line +
        headers at construction time — the body arrives separately,
        asynchronously, and has to be appended before anything reads
        past `self._offset` (`serialize_json`/`serialize_dto`).
        """
        if chunk:
            self._request += chunk

    def serialize_preambule(self) -> Preambule:
        method_start = method_end = self._offset

        while self._request[method_end] != SP:
            method_end += 1

        method = METHODS[self._request[method_start:method_end].decode()]

        url_start = url_end = method_end + 1

        while self._request[url_end] != SP:
            url_end += 1

        raw_url = self._request[url_start:url_end].decode()

        self._offset = url_end

        while self._request[self._offset] != LF:
            self._offset += 1

        path, _, query = raw_url.partition("?")

        return Preambule(path, method, query)

    def serialize_request(self) -> Request:
        headers: list[tuple[str, str]] = []
        cookies: list[tuple[str, str]] = []

        value_end = self._offset - 1
        key_start = key_end = value_start = self._offset
        while self._request[self._offset : self._offset + 2] != b"\r\n":
            if self._request[self._offset] == CN:
                key_start = value_end + 2
                key_end = self._offset

                if self._request[key_start:key_end] != b"Cookie":
                    value_end = self._offset
                    while self._request[self._offset] != CR:
                        value_end += 1
                        self._offset += 1

                    value_start = key_end + 2

                    headers.append(
                        (
                            self._request[key_start:key_end].decode(),
                            self._request[value_start:value_end].decode(),
                        )
                    )
                else:
                    self._offset += 2
                    while self._request[self._offset] != CR:
                        key_start = self._offset

                        while self._request[self._offset] != DC:
                            self._offset += 1

                        key_end = self._offset

                        value_start = self._offset + 1

                        while self._request[self._offset] not in {
                            SC,
                            CR,
                        }:
                            self._offset += 1

                        value_end = self._offset

                        if self._request[self._offset] == SC:
                            self._offset += 2

                        cookies.append(
                            (
                                self._request[key_start:key_end].decode(),
                                self._request[value_start:value_end].decode(),
                            )
                        )

            self._offset += 1

        return Request(
            headers,
            cookies,
        )

    def serialize_json(self) -> dict[str, Any]:
        try:
            parsed = json.loads(self._request[self._offset :])
        except json.JSONDecodeError as exc:
            msg = f"Malformed JSON body: {exc}."
            raise SerializationError(msg) from exc

        if not isinstance(parsed, dict):
            msg = "JSON body must be an object."
            raise SerializationError(msg)

        return parsed

    def serialize_dto[T: tuple[ALLOWED_TYPES, ...]](
        self,
        dto_type: type[T],
        path_params: dict[str, str],
        query_params: dict[str, list[str]],
    ) -> T:
        """Build the controller's `dto` (2nd argument) from the
        request. Each field of `dto_type` is resolved by the `Marker`
        carried in its `Annotated[X, ...]` metadata:
          - `Body[X]`  -> looked up in the JSON body, coerced to X
          - `Query[X]` -> looked up in the '?' query string, coerced to X
          - anything else -> a path parameter (from the matched route)

        `Body[X] | None` / `Query[X] | None` fields are optional.
        For `Body`, an explicit JSON `null` resolves to `None`, but
        an absent key is still a bad request. For `Query` (which has
        no `null` of its own), an absent key resolves to `None`.
        `validate_dto_type` guarantees path fields are never optional
        and that no field carries a default, so neither case is
        handled here.

        A repeated query key (`?a=1&a=2`) collects into `Query[list[X]]`,
        each item coerced to `X`. A non-list `Query[X]` field is a bad
        request if the key repeats — there's no sane single value to
        pick.

        A body key matching no `Body[...]` field is a bad request too
        (see `_reject_unknown_keys`). Extra query keys, by contrast,
        are ignored: a query string routinely carries unrelated
        parameters (tracking tags, cache busters) that were never
        meant for the DTO.
        """
        body: dict[str, Any] | None = None
        body_names: set[str] = set()
        values: dict[str, Any] = {}

        for field in resolve_dto_fields(dto_type):
            if field.source is FieldSource.BODY:
                if body is None:
                    body = self.serialize_json()
                body_names.add(field.name)
                raw = self._field(body, field.name, dto_type)
                values[field.name] = (
                    raw if raw is None else self._coerce(raw, field.target)
                )
            elif field.source is FieldSource.QUERY:
                if field.optional and field.name not in query_params:
                    values[field.name] = None
                    continue
                raw_values = self._field(query_params, field.name, dto_type)
                values[field.name] = self._coerce_query(
                    field.name, raw_values, field.target, dto_type
                )
            else:
                raw = self._field(path_params, field.name, dto_type)
                values[field.name] = self._coerce(raw, field.target)

        if body is not None:
            self._reject_unknown_keys(body, body_names, dto_type)

        self._validate_dto_values(values, dto_type)
        return dto_type(**values)

    def _reject_unknown_keys(
        self,
        body: dict[str, Any],
        known: set[str],
        dto_type: type,
    ) -> None:
        """Reject a JSON body carrying keys no field of `dto_type`
        resolves from.

        Dropping them silently makes a client that sent
        `{"username": "max", "role": "admin"}` look like it set a role,
        when the value never reached the controller — the same failure
        mode as a misspelled key, except a misspelled *required* key at
        least surfaces as the matching `Missing field` error. Nothing is
        lost by being strict here: every `Body` field has to be present
        anyway (an `Optional` one included — see above), so a key that
        matches no field could never have been honored.
        """
        unknown = sorted(set(body) - known)
        if unknown:
            names = ", ".join(repr(name) for name in unknown)
            msg = f"Unknown body field(s) {names} for {dto_type.__name__}."
            raise SerializationError(msg)

    def _validate_dto_values(
        self,
        values: dict[str, Any],
        dto_type: type,
    ) -> None:
        """Run every field's `validate(value)` against the values
        `serialize_dto` just coerced — the per-request counterpart to
        `assemble_dto_validators`, which only checked the rules
        themselves at startup. Duck-typed on `validate` the same way,
        so `StrField`, `IntField`, and friends are all picked up
        without this module importing any of them.
        """
        for field in resolve_dto_fields(dto_type):
            self._validate_field_value(values[field.name], field)

    def _validate_field_value(self, value: Any, field: DTOField) -> None:  # noqa: ANN401
        if value is None:
            return

        if isinstance(value, list):
            for item in value:
                self._validate_field_value(item, field)
            return

        if is_namedtuple(field.target):
            self._validate_dto_values(value._asdict(), field.target)
            return

        for item in field.metadata:
            validate = getattr(item, "validate", None)
            if callable(validate):
                validate(value)

    def _coerce_query(
        self,
        name: str,
        raw_values: list[str],
        target_type: Any,  # noqa: ANN401
        dto_type: type,
    ) -> Any:  # noqa: ANN401
        if get_origin(target_type) is list:
            (item_type,) = get_args(target_type)
            return [self._coerce(value, item_type) for value in raw_values]

        if len(raw_values) > 1:
            msg = (
                f"Query parameter '{name}' for {dto_type.__name__} was "
                f"repeated {len(raw_values)} times, expected a single "
                "value."
            )
            raise SerializationError(msg)

        return self._coerce(raw_values[0], target_type)

    def parse_query(self, query: str) -> dict[str, list[str]]:
        if not query:
            return {}

        params: dict[str, list[str]] = {}
        for pair in query.split("&"):
            name, _, value = pair.partition("=")
            if name:
                params.setdefault(name, []).append(value)

        return params

    def wrap_response(
        self,
        result: Any,  # noqa: ANN401
        status_code: int = 200,
    ) -> Response[Any]:
        """A controller may return a bare DTO instead of `Response[DTO]`
        when it only needs to set the body. Normalize both shapes to
        a `Response` here, once, instead of at every call site. A bare
        DTO gets the route's declared `status_code`; an explicit
        `Response` keeps its own.
        """
        if isinstance(result, Response):
            return result

        response: Response[Any] = Response(status_code=status_code)
        response.set_body(result)
        return response

    def render(
        self,
        response: Response[Any],
    ) -> tuple[list[tuple[bytes, bytes]], bytes]:
        """A `Response` turned into ASGI-ready (headers, body)."""
        headers = [
            (key.encode("latin-1"), value.encode("latin-1"))
            for key, value in response.header or ()
        ]
        for cookie in response.cookie or ():
            rendered = self.render_cookie(cookie).encode("latin-1")
            headers.append((b"set-cookie", rendered))

        body = self.render_body(response.body)

        # RFC 9110: 1xx/204/304 responses must not carry a body or
        # a Content-Length.
        has_body_status = (
            response.status_code >= 200  # noqa: PLR2004
            and response.status_code not in _NO_BODY_STATUSES
        )
        if body and has_body_status:
            has_content_type = any(
                name.lower() == b"content-type" for name, _ in headers
            )
            if not has_content_type:
                headers.append(
                    (b"content-type", self._content_type(response.body))
                )
            headers.append(
                (b"content-length", str(len(body)).encode("latin-1"))
            )

        return headers, body

    def _content_type(self, body: Any) -> bytes:  # noqa: ANN401
        """Mirrors `render_body`: a `str` is sent as-is, `bytes` as
        opaque bytes, anything else as JSON."""
        if isinstance(body, str):
            return _TEXT_CONTENT_TYPE

        if isinstance(body, bytes):
            return _BINARY_CONTENT_TYPE

        return _JSON_CONTENT_TYPE

    def render_body(self, body: Any) -> bytes:  # noqa: ANN401
        if body is None:
            return b""

        if isinstance(body, bytes):
            return body

        if isinstance(body, str):
            return body.encode("utf-8")

        return json.dumps(self._to_jsonable(body)).encode("utf-8")

    def render_cookie(self, cookie: Cookie) -> str:
        parts = [f"{cookie.key}={cookie.value}"]

        if cookie.max_age is not None:
            parts.append(f"Max-Age={cookie.max_age}")
        if cookie.expires is not None:
            expires = cookie.expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
            parts.append(f"Expires={expires}")
        if cookie.domain is not None:
            parts.append(f"Domain={cookie.domain}")
        if cookie.path is not None:
            parts.append(f"Path={cookie.path}")
        if cookie.secure:
            parts.append("Secure")
        if cookie.http_only:
            parts.append("HttpOnly")
        if cookie.same_site is not None:
            parts.append(f"SameSite={cookie.same_site}")
        if cookie.partitioned:
            parts.append("Partitioned")

        return "; ".join(parts)

    def _to_jsonable(self, value: Any) -> Any:  # noqa: ANN401
        return to_jsonable(value)

    def _field(
        self,
        source: dict[str, Any],
        name: str,
        dto_type: type,
    ) -> Any:  # noqa: ANN401
        try:
            return source[name]
        except KeyError:
            msg = f"Missing field '{name}' for {dto_type.__name__}."
            raise SerializationError(msg) from None

    def _coerce(self, value: Any, target_type: Any) -> Any:  # noqa: ANN401
        if is_enum(target_type):
            return self._coerce_enum(value, target_type)

        if is_namedtuple(target_type):
            if isinstance(value, dict):
                return self._coerce_namedtuple(value, target_type)

            msg = f"Cannot coerce {value!r} into {target_type!r}."
            raise SerializationError(msg)

        origin = get_origin(target_type) or target_type
        matches_origin = isinstance(origin, type) and isinstance(value, origin)
        # bool is an int subclass in Python; without this guard a
        # JSON `true`/`false` would silently pass as a valid int.
        is_bool_leak = origin is int and isinstance(value, bool)

        if matches_origin and not is_bool_leak:
            return value

        if isinstance(value, str):
            return self._coerce_str(value, target_type)

        msg = f"Cannot coerce {value!r} into {target_type!r}."
        raise SerializationError(msg)

    def _coerce_enum(self, value: Any, target_type: Any) -> Any:  # noqa: ANN401
        """Look an enum member up by its value. A query/path value
        always arrives as a string, so for an int-valued enum
        (`validate_enum_type` guarantees all-str or all-int) a string
        is parsed first — the same leniency `_coerce` already gives a
        plain `int` field.
        """
        candidate = value
        if isinstance(value, str) and all(
            isinstance(member.value, int) for member in target_type
        ):
            candidate = int(value) if value.lstrip("-").isdigit() else None

        # `bool` is an `int` subclass, so `IntEnum(True)` would quietly
        # resolve to the member valued `1`.
        if not isinstance(candidate, bool):
            try:
                return target_type(candidate)
            except ValueError:
                pass

        allowed = ", ".join(repr(member.value) for member in target_type)
        msg = (
            f"Cannot coerce {value!r} into {target_type.__name__}: "
            f"expected one of {allowed}."
        )
        raise SerializationError(msg)

    def _coerce_namedtuple(
        self,
        value: dict[str, Any],
        dto_type: type,
    ) -> Any:  # noqa: ANN401
        """Recursively build a `Body[NamedTuple]` field's target from
        its nested JSON object. `validate_dto_type` guarantees every
        field of `dto_type` is itself `Body[...]`, all the way down,
        so each one is resolved the same way a top-level `Body` field
        is: looked up by key, with an explicit JSON `null` passing
        through as `None`, and an unknown key in the nested object
        rejected just as it is at the top level.
        """
        values: dict[str, Any] = {}
        fields = resolve_dto_fields(dto_type)

        for field in fields:
            raw = self._field(value, field.name, dto_type)
            values[field.name] = (
                raw if raw is None else self._coerce(raw, field.target)
            )

        self._reject_unknown_keys(
            value, {field.name for field in fields}, dto_type
        )

        return dto_type(**values)

    def _coerce_str(self, raw: str, target_type: Any) -> Any:  # noqa: ANN401, PLR0911
        try:
            if target_type is int:
                return int(raw)
            if target_type is float:
                return float(raw)
            if target_type is bool:
                return raw.lower() in ("1", "true", "yes")
            if target_type is UUID:
                return UUID(raw)
            if target_type is datetime:
                return datetime.fromisoformat(raw)
            if target_type is bytes:
                return raw.encode("utf-8")
            if target_type is str:
                return raw
        except ValueError as exc:
            msg = f"Cannot parse {raw!r} as {target_type!r}: {exc}."
            raise SerializationError(msg) from exc

        msg = f"Unsupported target type for coercion: {target_type!r}."
        raise SerializationError(msg)


def to_jsonable(value: Any) -> Any:  # noqa: ANN401, PLR0911
    if isinstance(value, Enum):
        return value.value

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, bytes):
        return value.decode("utf-8")

    if hasattr(value, "_asdict"):
        return {
            key: to_jsonable(item)
            for key, item in value._asdict().items()
        }

    if isinstance(value, list | tuple | set | frozenset):
        return [to_jsonable(item) for item in value]

    if isinstance(value, dict):
        return {
            key: to_jsonable(item) for key, item in value.items()
        }

    return value
