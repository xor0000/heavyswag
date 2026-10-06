import inspect
import json
import re
from collections.abc import Sequence
from datetime import datetime
from enum import Enum
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Any, get_args, get_origin
from uuid import UUID

from heavyswag._internal._dto import (
    DTOField,
    FieldSource,
    dto_type,
    is_enum,
    is_namedtuple,
    output_dto_type,
    resolve_dto_fields,
)
from heavyswag._internal._serializer import to_jsonable
from heavyswag.doc.models import (
    APIKey,
    DocApp,
    DocController,
    DocField,
    DocParam,
    DocTag,
    HTTPBasic,
    HTTPBearer,
    SecurityScheme,
)
from heavyswag.errors import DocError, SerializationError, ValidationError
from heavyswag.specify.response import Response
from heavyswag.validation import DateTimeField, NumField, StrField
from heavyswag.validation.str_validation import _PATTERN_PRESETS

if TYPE_CHECKING:
    from heavyswag.routes.application import HeavySwag
    from heavyswag.routes.radix_tree import RouteEntry

OPENAPI_VERSION = "3.1.0"

_SCALAR_SCHEMAS: dict[type, dict[str, Any]] = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
    bytes: {"type": "string"},
    UUID: {"type": "string", "format": "uuid"},
    datetime: {"type": "string", "format": "date-time"},
}

_PRESET_FORMATS = {"email": "email", "url": "uri"}

# Raised by `Serializer.serialize_dto` for any route that reads at
# least one field — documented on every such route automatically.
_REQUEST_ERRORS: tuple[type[Exception], ...] = (
    SerializationError,
    ValidationError,
)

_PLAIN_YAML_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_YAML_RESERVED = frozenset(
    {"true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"}
)


def build_openapi(app: "HeavySwag") -> dict[str, Any]:
    """The OpenAPI 3.1 document for `app`, as a plain dict.

    The route tree is built first, so everything it checks at startup
    — DTO shapes, validator rules, `DocField` examples — has already
    passed by the time a single line of the document is written.
    """
    from heavyswag.routes.radix_tree import (  # noqa: PLC0415
        CompressedRadixTree,
        collect_routes,
    )

    CompressedRadixTree(main_router=app.main_router)
    return _OpenAPIBuilder(app).build(collect_routes(app.main_router))


def generate_swagger_file(app: "HeavySwag", file: str | Path) -> None:
    """Write the OpenAPI document for `app` to `file` — JSON for a
    `.json` file, YAML for `.yaml`/`.yml`."""
    path = Path(file)
    spec = build_openapi(app)

    if path.suffix == ".json":
        text = json.dumps(spec, ensure_ascii=False, indent=2) + "\n"
    elif path.suffix in {".yaml", ".yml"}:
        text = to_yaml(spec)
    else:
        msg = f"Unsupported swagger file extension {path.suffix!r}: use .json, .yaml or .yml."
        raise DocError(msg)

    path.write_text(text, encoding="utf-8")


class _OpenAPIBuilder:
    def __init__(self, app: "HeavySwag") -> None:
        self._app = app
        self._schemas: dict[str, dict[str, Any]] = {}
        self._schema_owners: dict[str, type] = {}
        self._tags: dict[str, DocTag] = {}
        self._security: dict[str, SecurityScheme] = {}

    def build(self, entries: Sequence["RouteEntry"]) -> dict[str, Any]:
        paths: dict[str, dict[str, Any]] = {}
        operations: list[tuple[dict[str, Any], RouteEntry]] = []

        visible = [
            entry
            for entry in entries
            if entry.route.doc is None or not entry.route.doc.hidden
        ]
        for entry in sorted(
            visible, key=lambda item: (item.path, item.route.method)
        ):
            operation = self._operation(entry)
            method = entry.route.method.name.lower()
            paths.setdefault(entry.path, {})[method] = operation
            operations.append((operation, entry))

        _assign_operation_ids(operations)

        spec: dict[str, Any] = {
            "openapi": OPENAPI_VERSION,
            "info": self._info(),
        }
        doc_app = self._app.doc
        if doc_app is not None and doc_app.servers:
            spec["servers"] = [
                _drop_none({"url": server.url, "description": server.description})
                for server in doc_app.servers
            ]
        if self._tags:
            spec["tags"] = [
                _drop_none({"name": tag.name, "description": tag.description})
                for tag in self._tags.values()
            ]
        spec["paths"] = paths

        components: dict[str, Any] = {}
        if self._schemas:
            components["schemas"] = dict(sorted(self._schemas.items()))
        if self._security:
            components["securitySchemes"] = {
                name: _security_scheme(scheme)
                for name, scheme in sorted(self._security.items())
            }
        if components:
            spec["components"] = components

        return spec

    def _info(self) -> dict[str, Any]:
        doc_app = self._app.doc or DocApp(title="HeavySwag API", version="0.1.0")
        info: dict[str, Any] = {
            "title": doc_app.title,
            "version": doc_app.version,
        }
        if doc_app.description is not None:
            info["description"] = doc_app.description
        if doc_app.contact is not None:
            info["contact"] = _drop_none(doc_app.contact._asdict())
        if doc_app.license_info is not None:
            info["license"] = _drop_none(doc_app.license_info._asdict())
        return info

    # operation

    def _operation(self, entry: "RouteEntry") -> dict[str, Any]:
        route = entry.route
        doc = route.doc or DocController()
        operation: dict[str, Any] = {}

        tags = [
            tag
            for router in entry.routers
            if router.doc is not None
            for tag in router.doc.tags
        ]
        tags.extend(doc.tags)
        if tags:
            operation["tags"] = list(dict.fromkeys(self._tag(tag) for tag in tags))

        summary, description = _docstring(route.controller, doc)
        if summary is not None:
            operation["summary"] = summary
        if description is not None:
            operation["description"] = description
        # Filled in once every operation is known — see
        # `_assign_operation_ids`.
        operation["operationId"] = None
        if doc.deprecated:
            operation["deprecated"] = True

        input_dto = dto_type(route.controller)
        fields = resolve_dto_fields(input_dto)
        parameters = [
            self._parameter(field)
            for field in fields
            if field.source is not FieldSource.BODY
        ]
        for location in ("header", "cookie"):
            parameters.extend(
                _doc_param(name, location, param)
                for name, param in _inherited_params(
                    entry, doc, location
                ).items()
            )
        if parameters:
            operation["parameters"] = parameters

        body_fields = [
            field for field in fields if field.source is FieldSource.BODY
        ]
        if body_fields:
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": self._object_schema(body_fields)
                    }
                },
            }

        operation["responses"] = self._responses(entry, doc, has_input=bool(fields))

        security = self._resolve_security(entry, doc)
        if security is not None:
            operation["security"] = [
                {self._register_security(scheme): []} for scheme in security
            ]

        return operation

    def _tag(self, tag: DocTag) -> str:
        known = self._tags.get(tag.name)
        if known is None:
            self._tags[tag.name] = tag
        elif known != tag:
            msg = f"Tag {tag.name!r} is declared with different descriptions."
            raise DocError(msg)
        return tag.name

    def _resolve_security(
        self, entry: "RouteEntry", doc: DocController
    ) -> Sequence[SecurityScheme] | None:
        if doc.security is not None:
            return doc.security

        for router in reversed(entry.routers):
            if router.doc is not None and router.doc.security is not None:
                return router.doc.security

        return None

    def _register_security(self, scheme: SecurityScheme) -> str:
        known = self._security.get(scheme.name)
        if known is None:
            self._security[scheme.name] = scheme
        elif known != scheme:
            msg = f"Security scheme {scheme.name!r} is declared twice with different settings."
            raise DocError(msg)
        return scheme.name

    def _parameter(self, field: DTOField) -> dict[str, Any]:
        parameter: dict[str, Any] = {
            "name": field.name,
            "in": str(field.source),
            "required": field.source is FieldSource.PATH or not field.optional,
            "schema": self._field_schema(field, with_doc=False),
        }

        doc = _doc_field(field)
        description = _join_lines(
            doc.description if doc else None, _rules_note(field.metadata)
        )
        if description is not None:
            parameter["description"] = description
        if doc is None:
            return parameter

        if doc.deprecated:
            parameter["deprecated"] = True
        if doc.examples is not None:
            parameter["examples"] = {
                name: {"value": to_jsonable(value)}
                for name, value in doc.examples.items()
            }
        elif doc.example is not None:
            parameter["example"] = to_jsonable(doc.example)

        return parameter

    # responses

    def _responses(
        self, entry: "RouteEntry", doc: DocController, *, has_input: bool
    ) -> dict[str, Any]:
        route = entry.route
        responses: dict[str, Any] = {}

        success: dict[str, Any] = {
            "description": doc.response_description
            or _phrase(route.status_code),
        }
        content = self._content(output_dto_type(route.controller))
        if content is not None:
            success["content"] = content
        if doc.response_headers:
            success["headers"] = {
                name: _response_header(header)
                for name, header in doc.response_headers.items()
            }
        responses[str(route.status_code)] = success

        raised = list(_REQUEST_ERRORS) if has_input else []
        raised.extend(doc.raises)

        grouped: dict[int, list[tuple[type[Exception], str]]] = {}
        for exc_type in dict.fromkeys(raised):
            mapped = self._app.err_handler.lookup(exc_type)
            if mapped is None:
                msg = (
                    f"Route '{route.method.name} {entry.path}' raises "
                    f"{exc_type.__name__}, which isn't registered in the "
                    "ErrorHandler — it would surface as a 500."
                )
                raise DocError(msg)

            status_code, message = mapped
            if status_code == route.status_code:
                msg = (
                    f"Route '{route.method.name} {entry.path}' raises "
                    f"{exc_type.__name__} with status {status_code}, the "
                    "same status as its successful response."
                )
                raise DocError(msg)

            grouped.setdefault(status_code, []).append((exc_type, message))

        for status_code, errors in sorted(grouped.items()):
            responses[str(status_code)] = self._error_response(status_code, errors)

        return responses

    def _error_response(
        self, status_code: int, errors: list[tuple[type[Exception], str]]
    ) -> dict[str, Any]:
        err_handler = self._app.err_handler
        messages = list(dict.fromkeys(message for _, message in errors))

        if err_handler.body_type is None:
            media_type = "text/plain"
            schema: dict[str, Any] = {"type": "string"}
        else:
            media_type = "application/json"
            schema = self._type_schema(err_handler.body_type)

        examples: dict[str, Any] = {}
        for exc_type, message in errors:
            example = _error_example(err_handler, exc_type, status_code, message)
            if example is not None:
                examples[exc_type.__name__] = {"value": example}

        media: dict[str, Any] = {"schema": schema}
        if examples:
            media["examples"] = examples

        return {
            "description": " / ".join(messages),
            "content": {media_type: media},
        }

    def _content(self, target: Any) -> dict[str, Any] | None:  # noqa: ANN401
        if target is None or target is type(None) or target is Response:
            return None

        if target is str:
            return {"text/plain": {"schema": {"type": "string"}}}

        if target is bytes:
            return {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}

        return {"application/json": {"schema": self._type_schema(target)}}

    # schemas

    def _object_schema(self, fields: Sequence[DTOField]) -> dict[str, Any]:
        # Every key is required on the wire — an `Optional` field still
        # has to be sent, as an explicit `null` — and an unknown key is
        # a bad request (`Serializer._reject_unknown_keys`).
        return {
            "type": "object",
            "properties": {
                field.name: self._field_schema(field, with_doc=True)
                for field in fields
            },
            "required": [field.name for field in fields],
            "additionalProperties": False,
        }

    def _field_schema(self, field: DTOField, *, with_doc: bool) -> dict[str, Any]:
        target = field.target
        is_list = get_origin(target) is list
        item_type = get_args(target)[0] if is_list else target

        item_schema = dict(self._type_schema(item_type))
        item_schema.update(_validator_constraints(field.metadata))
        schema: dict[str, Any] = (
            {"type": "array", "items": item_schema} if is_list else item_schema
        )

        # A `null` only ever travels in a JSON body — an absent key
        # is what makes an optional query parameter `None`. A bare
        # field nested in a body NamedTuple reports `PATH` as its
        # source, but is just as much a JSON key.
        nullable = field.optional and field.source is not FieldSource.QUERY
        if nullable:
            schema = _nullable(schema)

        doc = _doc_field(field)
        if with_doc:
            description = _join_lines(
                doc.description if doc else None, _rules_note(field.metadata)
            )
            if description is not None:
                schema["description"] = description
            if doc is not None:
                if doc.title is not None:
                    schema["title"] = doc.title
                if doc.deprecated:
                    schema["deprecated"] = True
                examples = doc.doc_examples()
                if examples:
                    schema["examples"] = [to_jsonable(value) for value in examples]

        return schema

    def _type_schema(self, target: Any) -> dict[str, Any]:  # noqa: ANN401
        if get_origin(target) is list:
            (item_type,) = get_args(target)
            return {"type": "array", "items": self._type_schema(item_type)}

        scalar = _SCALAR_SCHEMAS.get(target)
        if scalar is not None:
            return dict(scalar)

        if is_enum(target):
            return self._component(target, _enum_schema)

        if is_namedtuple(target):
            return self._component(target, self._namedtuple_schema)

        msg = f"Cannot document type {target!r}."
        raise DocError(msg)

    def _component(self, target: type, build: Any) -> dict[str, Any]:  # noqa: ANN401
        name = target.__name__
        owner = self._schema_owners.get(name)
        if owner is None:
            self._schema_owners[name] = target
            self._schemas[name] = {}
            self._schemas[name] = build(target)
        elif owner is not target:
            msg = (
                f"Two different types are both named {name!r} "
                f"({owner.__module__} and {target.__module__}) — rename "
                "one, OpenAPI schemas are keyed by name."
            )
            raise DocError(msg)

        return {"$ref": f"#/components/schemas/{name}"}

    def _namedtuple_schema(self, target: type) -> dict[str, Any]:
        schema = self._object_schema(resolve_dto_fields(target))
        description = inspect.getdoc(target)
        # `NamedTuple` generates a `Name(a, b)` docstring of its own.
        if description and not description.startswith(f"{target.__name__}("):
            schema["description"] = description
        return schema


# helpers


def _assign_operation_ids(
    operations: list[tuple[dict[str, Any], "RouteEntry"]],
) -> None:
    """An explicit `operation_id` is kept as-is; otherwise the
    controller's name is used, falling back to `<name>_<method>_<path>`
    when that name is taken by another operation."""
    candidates = [
        (entry.route.doc or DocController()).operation_id
        or entry.route.controller.__name__
        for _, entry in operations
    ]
    counts = {name: candidates.count(name) for name in candidates}

    seen: set[str] = set()
    for (operation, entry), name in zip(operations, candidates, strict=True):
        is_explicit = (entry.route.doc or DocController()).operation_id
        operation_id = name
        if not is_explicit and counts[name] > 1:
            method = entry.route.method.name.lower()
            operation_id = f"{name}_{method}_{_slug(entry.path)}"

        if operation_id in seen:
            msg = (
                f"Duplicate operation_id {operation_id!r} — set "
                "DocController(operation_id=...) explicitly."
            )
            raise DocError(msg)

        seen.add(operation_id)
        operation["operationId"] = operation_id


def _doc_field(field: DTOField) -> DocField | None:
    for item in field.metadata:
        if isinstance(item, DocField):
            item.assembly()
            return item
    return None


def _docstring(controller: Any, doc: DocController) -> tuple[str | None, str | None]:  # noqa: ANN401
    """`summary` defaults to the docstring's first line and
    `description` to the rest of it — or to all of it, once `summary`
    is given explicitly."""
    text = inspect.getdoc(controller)
    if not text:
        return doc.summary, doc.description

    if doc.summary is not None:
        return doc.summary, doc.description or text

    first, _, rest = text.partition("\n")
    return first.strip(), doc.description or (rest.strip() or None)


def _validator_constraints(metadata: Sequence[Any]) -> dict[str, Any]:
    constraints: dict[str, Any] = {}

    for item in metadata:
        if isinstance(item, StrField):
            constraints.update(_str_constraints(item))
        elif isinstance(item, NumField):
            constraints.update(_num_constraints(item))

    return constraints


def _str_constraints(field: StrField) -> dict[str, Any]:
    pattern = field.pattern
    if field.pattern_preset is not None:
        pattern = _PATTERN_PRESETS[field.pattern_preset]

    return _drop_none(
        {
            "minLength": field.min_len,
            "maxLength": field.max_len,
            "pattern": pattern,
            "format": _PRESET_FORMATS.get(field.pattern_preset or ""),
        }
    )


def _num_constraints(field: NumField[Any]) -> dict[str, Any]:
    return _drop_none(
        {
            "minimum": field.min,
            "maximum": field.max,
            "multipleOf": 2 if field.is_even else None,
        }
    )


# Validator settings JSON Schema has a keyword for — everything else a
# validator enforces is spelled out in the field's description instead.
_SCHEMA_KEYWORD_RULES: dict[type, frozenset[str]] = {
    StrField: frozenset({"min_len", "max_len", "pattern", "pattern_preset"}),
    NumField: frozenset({"min", "max", "is_even"}),
    DateTimeField: frozenset(),
}


def _rules_note(metadata: Sequence[Any]) -> str | None:
    rules: list[str] = []
    for item in metadata:
        covered = _SCHEMA_KEYWORD_RULES.get(type(item))
        if covered is None:
            continue
        for name, value in item._asdict().items():
            if value is not None and name not in covered:
                rules.append(f"{name}={to_jsonable(value)}")

    if not rules:
        return None

    return "Constraints: " + ", ".join(rules)


def _join_lines(*parts: str | None) -> str | None:
    present = [part for part in parts if part]
    return "\n\n".join(present) if present else None


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in schema:
        return {"anyOf": [schema, {"type": "null"}]}

    return {**schema, "type": [schema["type"], "null"]}


def _enum_schema(target: type[Enum]) -> dict[str, Any]:
    values = [member.value for member in target]
    kind = "string" if all(isinstance(value, str) for value in values) else "integer"
    return {"type": kind, "enum": values}


def _inherited_params(
    entry: "RouteEntry", doc: DocController, location: str
) -> dict[str, DocParam]:
    """`DocRouter`/`DocController` `headers` or `cookies`, from the
    main router down to the route — a nearer one replaces a farther
    one of the same name."""
    params: dict[str, DocParam] = {}
    for owner in [*(router.doc for router in entry.routers), doc]:
        declared = None if owner is None else getattr(owner, f"{location}s")
        params.update(declared or {})
    return params


def _doc_param(name: str, location: str, param: DocParam) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "in": location,
        "required": param.required,
        "schema": {"type": "string"},
    }
    if param.description is not None:
        result["description"] = param.description
    if param.deprecated:
        result["deprecated"] = True
    if param.example is not None:
        result["example"] = param.example
    return result


def _response_header(header: DocParam) -> dict[str, Any]:
    result: dict[str, Any] = {"schema": {"type": "string"}}
    if header.description is not None:
        result["description"] = header.description
    if header.required:
        result["required"] = True
    if header.example is not None:
        result["example"] = header.example
    return result


def _error_example(
    err_handler: Any,  # noqa: ANN401
    exc_type: type[Exception],
    status_code: int,
    message: str,
) -> Any:  # noqa: ANN401
    """What the client gets for `exc_type`. The exception is created
    without running its `__init__` — a custom one may need arguments
    there's no way to guess — so a body factory reading attributes it
    sets may fail; the example is then just left out."""
    try:
        exc = exc_type.__new__(exc_type)
        return to_jsonable(err_handler.build_body(exc, status_code, message))
    except Exception:  # noqa: BLE001
        return None


def _security_scheme(scheme: SecurityScheme) -> dict[str, Any]:
    if isinstance(scheme, HTTPBearer):
        result = {"type": "http", "scheme": "bearer", "bearerFormat": scheme.bearer_format}
    elif isinstance(scheme, HTTPBasic):
        result = {"type": "http", "scheme": "basic"}
    elif isinstance(scheme, APIKey):
        result = {"type": "apiKey", "in": scheme.location, "name": scheme.param_name}
    else:
        msg = f"Unknown security scheme {scheme!r}."
        raise DocError(msg)

    result["description"] = scheme.description
    return _drop_none(result)


def _phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return f"Status {status_code}"


def _slug(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_") or "root"


def _drop_none(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


# yaml


def to_yaml(value: Any) -> str:  # noqa: ANN401
    """A dependency-free YAML emitter for the JSON-shaped document
    `build_openapi` returns. Every string is written JSON-quoted —
    a JSON string literal is a valid YAML double-quoted scalar — so
    there's no YAML quoting rule to get wrong."""
    return "\n".join(_yaml_lines(value, 0)) + "\n"


def _yaml_lines(value: Any, indent: int) -> list[str]:  # noqa: ANN401
    pad = " " * indent

    if isinstance(value, dict) and value:
        lines: list[str] = []
        for key, item in value.items():
            head = f"{pad}{_yaml_key(key)}:"
            if _is_block(item):
                lines.append(head)
                lines.extend(_yaml_lines(item, indent + 2))
            else:
                lines.append(f"{head} {_yaml_scalar(item)}")
        return lines

    if isinstance(value, list) and value:
        lines = []
        for item in value:
            if _is_block(item):
                nested = _yaml_lines(item, indent + 2)
                nested[0] = f"{pad}- {nested[0][indent + 2 :]}"
                lines.extend(nested)
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}")
        return lines

    return [f"{pad}{_yaml_scalar(value)}"]


def _is_block(value: Any) -> bool:  # noqa: ANN401
    return isinstance(value, dict | list) and bool(value)


def _yaml_key(key: str) -> str:
    if _PLAIN_YAML_KEY.match(key) and key.lower() not in _YAML_RESERVED:
        return key
    return json.dumps(key, ensure_ascii=False)


def _yaml_scalar(value: Any) -> str:  # noqa: ANN401
    if isinstance(value, dict):
        return "{}"
    if isinstance(value, list):
        return "[]"
    return json.dumps(value, ensure_ascii=False)
