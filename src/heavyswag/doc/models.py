from collections.abc import Mapping, Sequence
from typing import Any, Literal, NamedTuple

from heavyswag.errors import DocError


class DocField(NamedTuple):
    """Documentation for one DTO field, put next to its validators:
    `Annotated[Body[str], StrField(...), DocField(...)]`.

    `example` is a single sample value; `examples` is a set of named
    ones (`{"short": "alex"}`) — they're mutually exclusive. Every
    example of an *input* DTO field is run through the field's own
    validators at startup (see `assemble_dto_validators`), so the docs
    can't advertise a value the route would reject.

    Deliberately has no `validate` method — that's what marks a
    validator, and a response DTO rejects those
    (`validate_output_dto_type`).
    """

    title: str | None = None
    description: str | None = None
    example: Any = None
    examples: Mapping[str, Any] | None = None
    deprecated: bool = False

    def assembly(self) -> None:
        """Consistency check during radix tree construction"""

        if self.example is not None and self.examples is not None:
            msg = "DocField: example and examples are mutually exclusive"
            raise DocError(msg)

        if self.examples is not None and not self.examples:
            msg = "DocField: examples must not be empty"
            raise DocError(msg)

    def doc_examples(self) -> tuple[Any, ...]:
        if self.examples is not None:
            return tuple(self.examples.values())

        if self.example is not None:
            return (self.example,)

        return ()


class DocParam(NamedTuple):
    """A request header or cookie — or a header the server sends back
    in a successful response (e.g. `Location` after a `201`).

    Documentation only: headers and cookies are never DTO fields, a
    controller reads them off `Request` itself, so nothing here is
    parsed or validated at runtime.
    """

    description: str | None = None
    example: str | None = None
    required: bool = False
    deprecated: bool = False


class DocTag(NamedTuple):
    name: str
    description: str | None = None


class HTTPBearer(NamedTuple):
    """`Authorization: Bearer <token>`. `name` is the scheme's key in
    `components.securitySchemes` — two schemes sharing it must be
    identical."""

    name: str = "bearerAuth"
    bearer_format: str | None = None
    description: str | None = None


class HTTPBasic(NamedTuple):
    name: str = "basicAuth"
    description: str | None = None


class APIKey(NamedTuple):
    """An API key carried in a header, query parameter or cookie
    called `param_name`."""

    param_name: str
    location: Literal["header", "query", "cookie"] = "header"
    name: str = "apiKeyAuth"
    description: str | None = None


type SecurityScheme = HTTPBearer | HTTPBasic | APIKey


class DocController(NamedTuple):
    """Documentation for one route, passed as `@router.get(..., doc=)`.

    Everything here is optional — the path, parameters, request body,
    success response and the `400` for a malformed request are all
    derived from the controller itself. `summary` and `description`
    default to the docstring's first line and the rest of it.

    `raises` lists the exceptions the route (or a middleware in front
    of it) may raise; each one is looked up in the app's
    `ErrorHandler`, which decides both the status code and the body,
    so the docs always describe what the client actually gets.

    `headers` and `cookies` document what the controller reads off
    `Request`; they're added to the ones inherited from the routers.

    `security=None` inherits from the routers; `security=()` marks
    the route as explicitly public.

    `hidden=True` leaves the route out of the document altogether —
    e.g. the route serving the documentation page itself. It's still
    served as usual; only the docs don't mention it.
    """

    summary: str | None = None
    description: str | None = None
    operation_id: str | None = None
    tags: Sequence[DocTag] = ()
    deprecated: bool = False
    security: Sequence[SecurityScheme] | None = None
    raises: Sequence[type[Exception]] = ()
    headers: Mapping[str, DocParam] | None = None
    cookies: Mapping[str, DocParam] | None = None
    response_description: str | None = None
    response_headers: Mapping[str, DocParam] | None = None
    hidden: bool = False


class DocRouter(NamedTuple):
    """Documentation shared by every route of a router — and of the
    routers included into it. `tags`, `headers` and `cookies` add up
    down the tree (a nearer one replaces a same-named farther one);
    the nearest `security` that isn't `None` wins."""

    tags: Sequence[DocTag] = ()
    security: Sequence[SecurityScheme] | None = None
    headers: Mapping[str, DocParam] | None = None
    cookies: Mapping[str, DocParam] | None = None


class DocContact(NamedTuple):
    name: str | None = None
    url: str | None = None
    email: str | None = None


class DocLicense(NamedTuple):
    name: str
    identifier: str | None = None
    url: str | None = None


class DocServer(NamedTuple):
    url: str
    description: str | None = None


class DocApp(NamedTuple):
    title: str
    version: str
    description: str | None = None
    contact: DocContact | None = None
    license_info: DocLicense | None = None
    servers: Sequence[DocServer] = ()


class DocUI(NamedTuple):
    """How the HTML documentation page (`generate_docs_html`) looks —
    the page, not the API it describes, so it lives apart from
    `DocApp`.

    `name` defaults to the API title. `logo` and `favicon` are either
    a short text (initials, an emoji) or an image URL / `data:` URI.
    `accent` is a `#rgb` / `#rrggbb` color; `accent_soft` (the second
    stop of the logo gradient) defaults to a lighter shade of it.
    """

    name: str | None = None
    logo: str | None = None
    accent: str = "#ff6b35"
    accent_soft: str | None = None
    favicon: str | None = None
