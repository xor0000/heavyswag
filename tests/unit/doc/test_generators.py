import json
from datetime import datetime
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Annotated, Any, NamedTuple
from uuid import UUID

import pytest

from heavyswag.doc import (
    APIKey,
    DocApp,
    DocContact,
    DocController,
    DocField,
    DocLicense,
    DocParam,
    DocRouter,
    DocServer,
    DocTag,
    HTTPBasic,
    HTTPBearer,
    build_openapi,
    generate_swagger_file,
)
from heavyswag.doc.generators import to_yaml
from heavyswag.errors import DocError, RouteTreeError
from heavyswag.middlewares.setups.err_handler import ErrorHandler
from heavyswag.routes.application import HeavySwag
from heavyswag.routes.router import HeavyRouter
from heavyswag.specify.request import Body, Query, Request
from heavyswag.specify.response import Response
from heavyswag.validation import DateTimeField, NumField, StrField


class _Empty(NamedTuple):
    pass


class _Role(StrEnum):
    ADMIN = "admin"
    USER = "user"


class _Level(IntEnum):
    LOW = 1
    HIGH = 2


class _Address(NamedTuple):
    """Where the user lives."""

    city: Annotated[str, DocField(example="Berlin")]
    zip_code: str | None


class _CreateUser(NamedTuple):
    username: Annotated[
        Body[str],
        StrField(min_len=3, max_len=13, has_digits=True),
        DocField(title="Name", description="Login", examples={"a": "alex1"}),
    ]
    email: Annotated[Body[str], StrField(pattern_preset="email")]
    age: Annotated[Body[int], NumField[int](min=18, max=99, is_even=True)]
    role: Body[_Role]
    address: Body[_Address] | None
    tags: Body[list[str]]
    level: Annotated[
        Query[_Level] | None,
        DocField(description="Level", example=_Level.HIGH, deprecated=True),
    ]
    ids: Query[list[UUID]]


class _UserOut(NamedTuple):
    id: UUID
    role: _Role


class _UserPath(NamedTuple):
    user_id: Annotated[int, DocField(description="User id")]


class _TakenError(Exception):
    pass


class _ForbiddenError(Exception):
    pass


class _LockedError(Exception):
    pass


def _app(router: HeavyRouter, **kwargs: Any) -> HeavySwag:  # noqa: ANN401
    return HeavySwag(main_router=router, **kwargs)


def _single_operation(spec: dict[str, Any]) -> dict[str, Any]:
    ((_, operations),) = spec["paths"].items()
    ((_, operation),) = operations.items()
    return operation  # type: ignore[no-any-return]


def _build_users_app(**kwargs: Any) -> HeavySwag:  # noqa: ANN401
    router = HeavyRouter("/")

    @router.post("/users", status_code=201)
    async def create_user(_: Request, __: _CreateUser) -> _UserOut:
        """Create a user.

        Registers a new user account.
        """
        raise NotImplementedError

    return _app(router, **kwargs)


# document


def test_build_openapi_uses_default_info_without_doc_app() -> None:
    spec = build_openapi(_build_users_app())

    assert spec["openapi"] == "3.1.0"
    assert spec["info"] == {"title": "HeavySwag API", "version": "0.1.0"}
    assert "servers" not in spec
    assert "tags" not in spec


def test_build_openapi_renders_doc_app() -> None:
    doc = DocApp(
        title="Demo",
        version="1.2.3",
        description="About",
        contact=DocContact(name="Team", email="team@example.com"),
        license_info=DocLicense(name="MIT"),
        servers=[DocServer("https://api.example.com", "prod")],
    )

    spec = build_openapi(_build_users_app(doc=doc))

    assert spec["info"] == {
        "title": "Demo",
        "version": "1.2.3",
        "description": "About",
        "contact": {"name": "Team", "email": "team@example.com"},
        "license": {"name": "MIT"},
    }
    assert spec["servers"] == [
        {"url": "https://api.example.com", "description": "prod"}
    ]


def test_build_openapi_validates_the_route_tree_first() -> None:
    router = HeavyRouter("/")

    @router.get("/items")
    async def items(_: Request, __: _UserPath) -> None:
        return None

    with pytest.raises(RouteTreeError, match="has no '\\{user_id\\}'"):
        build_openapi(_app(router))


def test_build_openapi_rejects_doc_example_failing_its_validator() -> None:
    class _Dto(NamedTuple):
        name: Annotated[Body[str], StrField(max_len=2), DocField(example="abc")]

    router = HeavyRouter("/")

    @router.post("/")
    async def create(_: Request, __: _Dto) -> None:
        return None

    with pytest.raises(RouteTreeError, match="documents example 'abc'"):
        build_openapi(_app(router))


# operation


def test_operation_summary_and_description_come_from_docstring() -> None:
    operation = _single_operation(build_openapi(_build_users_app()))

    assert operation["summary"] == "Create a user."
    assert operation["description"] == "Registers a new user account."
    assert operation["operationId"] == "create_user"


def test_explicit_summary_makes_whole_docstring_the_description() -> None:
    router = HeavyRouter("/")

    @router.get("/", doc=DocController(summary="List"))
    async def index(_: Request, __: _Empty) -> None:
        """Lists everything."""

    operation = _single_operation(build_openapi(_app(router)))

    assert operation["summary"] == "List"
    assert operation["description"] == "Lists everything."


def test_operation_without_docstring_has_no_summary() -> None:
    router = HeavyRouter("/")

    @router.get("/", doc=DocController(deprecated=True))
    async def index(_: Request, __: _Empty) -> None:
        return None

    operation = _single_operation(build_openapi(_app(router)))

    assert "summary" not in operation
    assert "description" not in operation
    assert operation["deprecated"] is True


def test_operation_ids_fall_back_to_method_and_path_when_shared() -> None:
    router = HeavyRouter("/")
    sub = HeavyRouter("/admin")
    router.include_router(sub)

    @router.get("/items")
    async def items(_: Request, __: _Empty) -> None:
        return None

    @sub.get("/items")
    async def items_admin(_: Request, __: _Empty) -> None:
        return None

    items_admin.__name__ = "items"

    spec = build_openapi(_app(router))

    assert spec["paths"]["/items"]["get"]["operationId"] == "items_get_items"
    assert (
        spec["paths"]["/admin/items"]["get"]["operationId"]
        == "items_get_admin_items"
    )


def test_duplicate_explicit_operation_id_is_rejected() -> None:
    router = HeavyRouter("/")

    @router.get("/a", doc=DocController(operation_id="same"))
    async def first(_: Request, __: _Empty) -> None:
        return None

    @router.get("/b", doc=DocController(operation_id="same"))
    async def second(_: Request, __: _Empty) -> None:
        return None

    with pytest.raises(DocError, match="Duplicate operation_id 'same'"):
        build_openapi(_app(router))


# parameters and body


def test_path_and_query_parameters() -> None:
    router = HeavyRouter("/")

    @router.get("/users/{user_id}")
    async def get_user(_: Request, __: _UserPath) -> None:
        return None

    operation = _single_operation(build_openapi(_app(router)))

    assert operation["parameters"] == [
        {
            "name": "user_id",
            "in": "path",
            "required": True,
            "schema": {"type": "integer"},
            "description": "User id",
        }
    ]


def test_query_parameters_carry_doc_and_are_not_nullable() -> None:
    spec = build_openapi(_build_users_app())
    level, ids = _single_operation(spec)["parameters"]

    assert level == {
        "name": "level",
        "in": "query",
        "required": False,
        "schema": {"$ref": "#/components/schemas/_Level"},
        "description": "Level",
        "deprecated": True,
        "example": 2,
    }
    assert ids == {
        "name": "ids",
        "in": "query",
        "required": True,
        "schema": {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
        },
    }


def test_request_body_schema() -> None:
    spec = build_openapi(_build_users_app())
    body = _single_operation(spec)["requestBody"]

    assert body["required"] is True
    schema = body["content"]["application/json"]["schema"]
    assert schema["required"] == [
        "username",
        "email",
        "age",
        "role",
        "address",
        "tags",
    ]
    assert schema["additionalProperties"] is False

    properties = schema["properties"]
    assert properties["username"] == {
        "type": "string",
        "minLength": 3,
        "maxLength": 13,
        "description": "Login\n\nConstraints: has_digits=True",
        "title": "Name",
        "examples": ["alex1"],
    }
    assert properties["email"]["format"] == "email"
    assert properties["email"]["pattern"].startswith("^")
    assert properties["age"] == {
        "type": "integer",
        "minimum": 18,
        "maximum": 99,
        "multipleOf": 2,
    }
    assert properties["role"] == {"$ref": "#/components/schemas/_Role"}
    assert properties["address"] == {
        "anyOf": [
            {"$ref": "#/components/schemas/_Address"},
            {"type": "null"},
        ]
    }
    assert properties["tags"] == {"type": "array", "items": {"type": "string"}}


def test_components_hold_enums_and_nested_namedtuples() -> None:
    schemas = build_openapi(_build_users_app())["components"]["schemas"]

    assert schemas["_Role"] == {"type": "string", "enum": ["admin", "user"]}
    assert schemas["_Level"] == {"type": "integer", "enum": [1, 2]}
    assert schemas["_Address"] == {
        "type": "object",
        "properties": {
            "city": {"type": "string", "examples": ["Berlin"]},
            "zip_code": {"type": ["string", "null"]},
        },
        "required": ["city", "zip_code"],
        "additionalProperties": False,
        "description": "Where the user lives.",
    }


def test_datetime_rules_are_spelled_out_in_description() -> None:
    class _Dto(NamedTuple):
        at: Annotated[Query[datetime], DateTimeField(is_future=True)]

    router = HeavyRouter("/")

    @router.get("/")
    async def index(_: Request, __: _Dto) -> None:
        return None

    (param,) = _single_operation(build_openapi(_app(router)))["parameters"]

    assert param["schema"] == {"type": "string", "format": "date-time"}
    assert param["description"] == "Constraints: is_future=True"


def test_same_named_types_are_rejected() -> None:
    def make() -> type:
        class _Twin(NamedTuple):
            value: str

        return _Twin

    first, second = make(), make()

    class _Dto(NamedTuple):
        a: Body[first]  # type: ignore[valid-type]
        b: Body[second]  # type: ignore[valid-type]

    router = HeavyRouter("/")

    @router.post("/")
    async def create(_: Request, __: _Dto) -> None:
        return None

    with pytest.raises(DocError, match="both named '_Twin'"):
        build_openapi(_app(router))


# headers and cookies


def test_headers_and_cookies_are_inherited_and_overridden() -> None:
    router = HeavyRouter(
        "/",
        doc=DocRouter(
            headers={
                "X-Request-Id": DocParam(description="outer"),
                "X-Tenant": DocParam(description="tenant", required=True),
            },
        ),
    )

    @router.get(
        "/",
        doc=DocController(
            headers={"X-Request-Id": DocParam(description="inner")},
            cookies={
                "session": DocParam(example="s1", deprecated=True),
            },
        ),
    )
    async def index(_: Request, __: _Empty) -> None:
        return None

    params = _single_operation(build_openapi(_app(router)))["parameters"]

    assert params == [
        {
            "name": "X-Request-Id",
            "in": "header",
            "required": False,
            "schema": {"type": "string"},
            "description": "inner",
        },
        {
            "name": "X-Tenant",
            "in": "header",
            "required": True,
            "schema": {"type": "string"},
            "description": "tenant",
        },
        {
            "name": "session",
            "in": "cookie",
            "required": False,
            "schema": {"type": "string"},
            "deprecated": True,
            "example": "s1",
        },
    ]


# responses


def test_success_response_uses_route_status_and_output_schema() -> None:
    responses = _single_operation(build_openapi(_build_users_app()))[
        "responses"
    ]

    assert responses["201"] == {
        "description": "Created",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/_UserOut"}
            }
        },
    }


@pytest.mark.parametrize(
    ("return_type", "content"),
    [
        (str, {"text/plain": {"schema": {"type": "string"}}}),
        (
            bytes,
            {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        ),
        (
            list[int],
            {
                "application/json": {
                    "schema": {"type": "array", "items": {"type": "integer"}}
                }
            },
        ),
        (Response[str], {"text/plain": {"schema": {"type": "string"}}}),
        (None, None),
    ],
)
def test_success_response_content_by_return_type(
    return_type: Any,  # noqa: ANN401
    content: dict[str, Any] | None,
) -> None:
    router = HeavyRouter("/")

    async def index(_: Request, __: _Empty) -> None:
        return None

    index.__annotations__["return"] = return_type
    router.get("/")(index)

    responses = _single_operation(build_openapi(_app(router)))["responses"]

    assert responses["200"].get("content") == content


def test_success_response_headers_and_description() -> None:
    router = HeavyRouter("/")

    @router.post(
        "/",
        status_code=201,
        doc=DocController(
            response_description="Done",
            response_headers={
                "Location": DocParam(
                    description="Where", example="/x/1", required=True
                )
            },
        ),
    )
    async def create(_: Request, __: _Empty) -> None:
        return None

    responses = _single_operation(build_openapi(_app(router)))["responses"]

    assert responses == {
        "201": {
            "description": "Done",
            "headers": {
                "Location": {
                    "schema": {"type": "string"},
                    "description": "Where",
                    "required": True,
                    "example": "/x/1",
                }
            },
        }
    }


def test_request_errors_are_documented_only_for_routes_reading_input() -> None:
    router = HeavyRouter("/")

    @router.get("/")
    async def index(_: Request, __: _Empty) -> None:
        return None

    @router.get("/users/{user_id}")
    async def get_user(_: Request, __: _UserPath) -> None:
        return None

    paths = build_openapi(_app(router))["paths"]

    assert set(paths["/"]["get"]["responses"]) == {"200"}
    assert paths["/users/{user_id}"]["get"]["responses"]["400"] == {
        "description": "Bad Request",
        "content": {
            "text/plain": {
                "schema": {"type": "string"},
                "examples": {
                    "SerializationError": {"value": "Bad Request"},
                    "ValidationError": {"value": "Bad Request"},
                },
            }
        },
    }


def test_raises_are_resolved_through_the_error_handler() -> None:
    router = HeavyRouter("/")

    @router.post(
        "/",
        doc=DocController(raises=[_TakenError, _ForbiddenError, _LockedError]),
    )
    async def create(_: Request, __: _Empty) -> None:
        return None

    handler = ErrorHandler(
        {
            _TakenError: (409, "Taken"),
            _ForbiddenError: (403, "Forbidden"),
            _LockedError: (409, "Locked"),
        }
    )

    responses = _single_operation(
        build_openapi(_app(router, err_handler=handler))
    )["responses"]

    assert list(responses) == ["200", "403", "409"]
    assert responses["409"]["description"] == "Taken / Locked"
    assert responses["409"]["content"]["text/plain"]["examples"] == {
        "_TakenError": {"value": "Taken"},
        "_LockedError": {"value": "Locked"},
    }


def test_unregistered_raise_is_rejected() -> None:
    router = HeavyRouter("/")

    @router.get("/", doc=DocController(raises=[_TakenError]))
    async def index(_: Request, __: _Empty) -> None:
        return None

    with pytest.raises(DocError, match="isn't registered in the ErrorHandler"):
        build_openapi(_app(router))


def test_raise_with_success_status_is_rejected() -> None:
    router = HeavyRouter("/")

    @router.get("/", doc=DocController(raises=[_TakenError]))
    async def index(_: Request, __: _Empty) -> None:
        return None

    handler = ErrorHandler({_TakenError: (200, "Oops")})

    with pytest.raises(DocError, match="same status as its successful"):
        build_openapi(_app(router, err_handler=handler))


class _ErrorBody(NamedTuple):
    code: str
    message: Annotated[str, DocField(example="Bad Request")]


def _error_body(exc: Exception, status_code: int, message: str) -> _ErrorBody:  # noqa: ARG001
    return _ErrorBody(code=type(exc).__name__, message=message)


def test_error_body_factory_documents_json_errors() -> None:
    router = HeavyRouter("/")

    @router.post("/", doc=DocController(raises=[_TakenError]))
    async def create(_: Request, __: _Empty) -> None:
        return None

    handler = ErrorHandler({_TakenError: (409, "Taken")}, body=_error_body)

    spec = build_openapi(_app(router, err_handler=handler))
    responses = _single_operation(spec)["responses"]

    assert responses["409"]["content"] == {
        "application/json": {
            "schema": {"$ref": "#/components/schemas/_ErrorBody"},
            "examples": {
                "_TakenError": {
                    "value": {"code": "_TakenError", "message": "Taken"}
                }
            },
        }
    }
    assert "_ErrorBody" in spec["components"]["schemas"]


def test_error_example_is_skipped_when_factory_fails() -> None:
    class _CodedError(Exception):
        def __init__(self, code: str) -> None:
            super().__init__(code)
            self.code = code

    class _Body(NamedTuple):
        code: str

    def body(exc: Exception, status_code: int, message: str) -> _Body:  # noqa: ARG001
        return _Body(code=exc.code)  # type: ignore[attr-defined]

    router = HeavyRouter("/")

    @router.post("/", doc=DocController(raises=[_CodedError]))
    async def create(_: Request, __: _Empty) -> None:
        return None

    handler = ErrorHandler({_CodedError: (409, "Coded")}, body=body)

    responses = _single_operation(
        build_openapi(_app(router, err_handler=handler))
    )["responses"]

    assert "examples" not in responses["409"]["content"]["application/json"]


# tags and security


def test_tags_add_up_down_the_router_tree() -> None:
    router = HeavyRouter("/", doc=DocRouter(tags=[DocTag("Api", "All")]))
    users = HeavyRouter("/users", doc=DocRouter(tags=[DocTag("Users")]))
    router.include_router(users)

    @users.get("/", doc=DocController(tags=[DocTag("Read")]))
    async def list_users(_: Request, __: _Empty) -> None:
        return None

    spec = build_openapi(_app(router))

    assert _single_operation(spec)["tags"] == ["Api", "Users", "Read"]
    assert spec["tags"] == [
        {"name": "Api", "description": "All"},
        {"name": "Users"},
        {"name": "Read"},
    ]


def test_conflicting_tag_descriptions_are_rejected() -> None:
    router = HeavyRouter("/", doc=DocRouter(tags=[DocTag("Users", "a")]))

    @router.get("/", doc=DocController(tags=[DocTag("Users", "b")]))
    async def index(_: Request, __: _Empty) -> None:
        return None

    with pytest.raises(DocError, match="Tag 'Users'"):
        build_openapi(_app(router))


def test_security_is_inherited_overridden_and_registered() -> None:
    bearer = HTTPBearer(bearer_format="JWT")
    api_key = APIKey("X-Api-Key", name="key")
    router = HeavyRouter("/", doc=DocRouter(security=[bearer]))

    @router.get("/private")
    async def private(_: Request, __: _Empty) -> None:
        return None

    @router.get("/public", doc=DocController(security=()))
    async def public(_: Request, __: _Empty) -> None:
        return None

    @router.get("/keyed", doc=DocController(security=[api_key, HTTPBasic()]))
    async def keyed(_: Request, __: _Empty) -> None:
        return None

    spec = build_openapi(_app(router))
    paths = spec["paths"]

    assert paths["/private"]["get"]["security"] == [{"bearerAuth": []}]
    assert paths["/public"]["get"]["security"] == []
    assert paths["/keyed"]["get"]["security"] == [
        {"key": []},
        {"basicAuth": []},
    ]
    assert spec["components"]["securitySchemes"] == {
        "basicAuth": {"type": "http", "scheme": "basic"},
        "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
        "key": {"type": "apiKey", "in": "header", "name": "X-Api-Key"},
    }


def test_route_without_any_security_has_no_security_key() -> None:
    router = HeavyRouter("/")

    @router.get("/")
    async def index(_: Request, __: _Empty) -> None:
        return None

    spec = build_openapi(_app(router))

    assert "security" not in _single_operation(spec)
    assert "components" not in spec


def test_conflicting_security_schemes_are_rejected() -> None:
    router = HeavyRouter(
        "/", doc=DocRouter(security=[HTTPBearer(bearer_format="JWT")])
    )

    @router.get("/", doc=DocController(security=[HTTPBearer()]))
    async def index(_: Request, __: _Empty) -> None:
        return None

    @router.get("/other")
    async def other(_: Request, __: _Empty) -> None:
        return None

    with pytest.raises(DocError, match="Security scheme 'bearerAuth'"):
        build_openapi(_app(router))


# files


def test_generate_swagger_file_writes_json(tmp_path: Path) -> None:
    app = _build_users_app()
    path = tmp_path / "openapi.json"

    generate_swagger_file(app, path)

    assert json.loads(path.read_text(encoding="utf-8")) == build_openapi(app)


@pytest.mark.parametrize("suffix", [".yaml", ".yml"])
def test_generate_swagger_file_writes_yaml(
    tmp_path: Path, suffix: str
) -> None:
    yaml = pytest.importorskip("yaml")
    app = _build_users_app(doc=DocApp(title="Демо", version="1"))
    path = tmp_path / f"openapi{suffix}"

    generate_swagger_file(app, path)

    assert yaml.safe_load(path.read_text(encoding="utf-8")) == build_openapi(
        app
    )


def test_generate_swagger_file_rejects_unknown_extension(
    tmp_path: Path,
) -> None:
    with pytest.raises(DocError, match="Unsupported swagger file extension"):
        generate_swagger_file(_build_users_app(), tmp_path / "openapi.txt")


def test_to_yaml_quotes_ambiguous_keys_and_scalars() -> None:
    yaml = pytest.importorskip("yaml")
    value = {
        "200": {"description": "OK"},
        "yes": True,
        "/users/{id}": [],
        "empty": {},
        "list": [{"a": 1, "b": [None, 1.5]}, "x: y", ""],
        "plain_key": "on",
    }

    assert yaml.safe_load(to_yaml(value)) == value
