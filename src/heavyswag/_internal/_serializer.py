import json
from datetime import datetime
from typing import Any, Final, get_args, get_origin, get_type_hints
from uuid import UUID

from heavyswag.constants import ALLOWED_TYPES, HttpMethod, MethodType
from heavyswag.errors import SerializationError
from heavyswag.specify.cookie import Cookie
from heavyswag.specify.request import Body, Preambule, Query, Request
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
        headers: dict[str, str] = {}
        cookies: dict[str, str] = {}

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

                    headers[self._request[key_start:key_end].decode()] = (
                        self._request[value_start:value_end].decode()
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

                        cookies[self._request[key_start:key_end].decode()] = (
                            self._request[value_start:value_end].decode()
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
        query_params: dict[str, str],
    ) -> T:
        """Build the controller's `dto` (2nd argument) from the
        request. Each field of `dto_type` is resolved by its
        annotation:
          - `Body[X]`  -> looked up in the JSON body, coerced to X
          - `Query[X]` -> looked up in the '?' query string, coerced to X
          - anything else -> a path parameter (from the matched route)
        """
        hints = get_type_hints(dto_type)
        body: dict[str, Any] | None = None
        values: dict[str, Any] = {}

        for name, hint in hints.items():
            origin = get_origin(hint)

            if origin is Body:
                if body is None:
                    body = self.serialize_json()
                raw = self._field(body, name, dto_type)
                values[name] = self._coerce(raw, get_args(hint)[0])
            elif origin is Query:
                raw = self._field(query_params, name, dto_type)
                values[name] = self._coerce(raw, get_args(hint)[0])
            else:
                raw = self._field(path_params, name, dto_type)
                values[name] = self._coerce(raw, hint)

        return dto_type(**values)

    def parse_query(self, query: str) -> dict[str, str]:
        if not query:
            return {}

        params: dict[str, str] = {}
        for pair in query.split("&"):
            name, _, value = pair.partition("=")
            if name:
                params[name] = value

        return params

    def wrap_response(self, result: Any) -> Response[Any]:  # noqa: ANN401
        """A controller may return a bare DTO instead of `Response[DTO]`
        when it only needs to set the body. Normalize both shapes to
        a `Response` here, once, instead of at every call site.
        """
        if isinstance(result, Response):
            return result

        response: Response[Any] = Response()
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
            response.status_code >= 200
            and response.status_code not in _NO_BODY_STATUSES
        )
        if body and has_body_status:
            headers.append(
                (b"content-length", str(len(body)).encode("latin-1"))
            )

        return headers, body

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
        if isinstance(value, UUID):
            return str(value)

        if isinstance(value, datetime):
            return value.isoformat()

        if isinstance(value, bytes):
            return value.decode("utf-8")

        if hasattr(value, "_asdict"):
            return {
                key: self._to_jsonable(item)
                for key, item in value._asdict().items()
            }

        if isinstance(value, list | tuple):
            return [self._to_jsonable(item) for item in value]

        if isinstance(value, dict):
            return {
                key: self._to_jsonable(item) for key, item in value.items()
            }

        return value

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
        origin = get_origin(target_type) or target_type
        matches_origin = isinstance(origin, type) and isinstance(
            value, origin
        )
        # bool is an int subclass in Python; without this guard a
        # JSON `true`/`false` would silently pass as a valid int.
        is_bool_leak = origin is int and isinstance(value, bool)

        if matches_origin and not is_bool_leak:
            return value

        if isinstance(value, str):
            return self._coerce_str(value, target_type)

        msg = f"Cannot coerce {value!r} into {target_type!r}."
        raise SerializationError(msg)

    def _coerce_str(self, raw: str, target_type: Any) -> Any:  # noqa: ANN401
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
