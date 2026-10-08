---
icon: lucide/book-open
---

# API documentation

HeavySwag documents your API from the same code that serves it. The DTOs
already say where every field comes from and what type it is, the
[validators](6_validation.md) already say which values are allowed, and the
controller's return type already says what comes back — so the generator
reads all of that directly. The `heavyswag.doc` annotations only add what
code can't express: human-readable descriptions, examples, tags, auth.

From one app you get either:

- an **OpenAPI 3.1** document (`openapi.yaml` / `openapi.json`) for any
  tool that speaks it — Swagger UI, code generators, API gateways;
- a **self-contained interactive HTML page** — browse the API, fill in a
  request, have it validated against the schema, send it, see the response.

```python
from pathlib import Path

from heavyswag.doc import DocUI, generate_docs_html, generate_swagger_file

DOCS_FILE = Path(__file__).with_name("docs.html")
DOCS_UI = DocUI(name="My API")

generate_swagger_file(app, "openapi.yaml")
generate_docs_html(app, DOCS_FILE, ui=DOCS_UI)
```

## What's derived for you

| In the document            | Comes from                                                                 |
| -------------------------- | -------------------------------------------------------------------------- |
| path, method               | the route and the router prefixes                                          |
| path / query parameters    | DTO fields without a marker / `Query[...]` fields                          |
| request body               | `Body[...]` fields — an object with every key required and no extra keys allowed |
| types                      | `str`, `int`, `UUID` (`format: uuid`), `datetime` (`format: date-time`), `list[T]`, `Enum`, nested `NamedTuple`s (as `components/schemas`) |
| `Optional`                 | a `Body` field: required key, `null` allowed; a `Query` field: not required |
| constraints                | the field's validators — see [below](#validators-become-the-schema)        |
| `summary` / `description`  | the controller's docstring — first line, then the rest                     |
| `operationId`              | the controller's name                                                      |
| success response           | the return type (`Response[T]` unwrapped); status `200`, or `DocController(success_status_code=...)` |
| `400 Bad Request`          | added to every route whose DTO has at least one field                      |
| error responses            | `raises=[...]`, resolved through the app's `ErrorHandler`                  |

So a route with no doc annotations at all is already documented:

```python
@router.get("/users/{user_id}")
async def get_user(request: Request, dto: UserPathDTO) -> UserOut:
    """Get a user.

    Returns the user with the given id.
    """
```

## Documenting fields

`DocField` sits in the same `Annotated` as the marker and the validators:

```python
from heavyswag.doc import DocField

class CreateUserDTO(NamedTuple):
    username: Annotated[
        Body[str],
        StrField(min_len=3, max_len=13, pattern=r"^[a-z0-9_]+$"),
        DocField(
            title="Username",
            description="Lower-case latin letters, digits and `_`",
            examples={"short": "alex", "with_digits": "alex_1"},
        ),
    ]
    age: Annotated[Body[int], NumField[int](min=18), DocField(example=18)]
```

| Argument      | Means                                                            |
| ------------- | ---------------------------------------------------------------- |
| `title`       | a short name, shown above the description                        |
| `description` | Markdown                                                         |
| `example`     | one sample value                                                 |
| `examples`    | several named ones — mutually exclusive with `example`           |
| `deprecated`  | marks the field as deprecated                                    |

It works the same on response DTOs — `DocField` deliberately has no
`validate()` method, so a response DTO doesn't mistake it for a validator.

### Examples are validated too

Every example of an input DTO field goes through that field's own validators
while the route tree is built — a wrong example is a startup error, not a
doc that lies:

```python
username: Annotated[
    Body[str],
    StrField(pattern=r"^[a-z0-9_]+$"),
    DocField(example="Алекс"),  # (1)!
]
```

1.  Rejected at startup with `RouteTreeError: DTO '...' field 'username'
    documents example 'Алекс', which its own validator rejects: String does
    not match pattern`.

### Validators become the schema

A validator's settings are translated into JSON Schema keywords — the very
same rules the server enforces show up in the document, and the HTML page
checks them before sending:

| Validator                   | JSON Schema                                         |
| --------------------------- | --------------------------------------------------- |
| `StrField(min_len, max_len)`| `minLength`, `maxLength`                            |
| `StrField(pattern=...)`     | `pattern`                                           |
| `StrField(pattern_preset=)` | the preset's `pattern`, plus `format: email` / `format: uri` for `email` / `url` |
| `NumField(min, max)`        | `minimum`, `maximum`                                |
| `NumField(is_even=True)`    | `multipleOf: 2`                                     |

!!! warning "Not every rule has a JSON Schema keyword"
    The rest — `StrField(has_digits=..., is_upper=..., no_consecutive_repeats=...)`,
    `NumField(is_odd=True)`, every `DateTimeField` rule — is spelled out in
    the field's description (`Constraints: has_digits=True`) instead. The
    server still enforces them with a `400`, but the HTML page can't check
    them before sending.

!!! note "Anchor your patterns"
    Python checks `pattern` with `re.fullmatch` (the whole string), while
    JSON Schema — and so the browser — accepts a match *anywhere* in the
    string. Write `^...$` so both sides agree.

## Documenting routes

```python
from heavyswag.doc import DocController, DocParam

@users.post(
    "/",
    doc=DocController(
        summary="Create a user",
        success_status_code=201,  # (1)!
        raises=[UnauthorizedError, UsernameTakenError],
        response_headers={
            "Location": DocParam(description="URL of the new user"),
        },
    ),
)
async def create_user(request: Request, dto: CreateUserDTO) -> Response[UserOut]:
    ...
    response: Response[UserOut] = Response(status_code=201, body=user)  # (2)!
    response.attach_header("Location", f"/users/{user.id}")
    return response
```

1.  Documentation only — it's what the docs show as the successful status.
2.  What's actually sent. A bare DTO is always a `200`; any other status is
    set explicitly, by returning a `Response`. Nothing ties the two
    together, so keep them in sync — the HTML page warns when a real
    response comes back with a status the docs don't mention.

| Argument               | Means                                                                 |
| ---------------------- | --------------------------------------------------------------------- |
| `summary`, `description` | override the docstring                                             |
| `operation_id`         | overrides the controller's name                                       |
| `tags`                 | extra tags, on top of the routers'                                    |
| `deprecated`           | marks the route as deprecated                                         |
| `security`             | see [Auth](#auth)                                                     |
| `raises`               | exceptions the route (or a middleware in front of it) may raise       |
| `headers`, `cookies`   | request headers / cookies the controller reads off `Request`          |
| `success_status_code`  | the successful response's status in the docs (`200` by default)       |
| `response_headers`     | headers the successful response carries                               |
| `response_description` | overrides the success response's description                          |
| `hidden`               | leaves the route out of the document — see [below](#hiding-a-route)   |

### Errors come from the `ErrorHandler`

`raises` lists exception classes, not status codes. Each one is looked up in
the app's `ErrorHandler` — the same lookup that turns it into a response at
runtime — so the status code and the body in the docs are exactly what the
client gets:

```python
app = HeavySwag(
    main_router=router,
    err_handler=ErrorHandler(
        {
            UsernameTakenError: (409, "Username already taken"),
            UnauthorizedError: (401, "Unauthorized"),
        },
        body=error_body,  # (1)!
    ),
)
```

1.  Optional. Without it an error body is the plain-text message. With it,
    every error is sent — and documented — as one JSON shape:

    ```python
    class ErrorDTO(NamedTuple):
        code: str
        message: str

    def error_body(exc: Exception, status_code: int, message: str) -> ErrorDTO:
        return ErrorDTO(code=type(exc).__name__, message=message)
    ```

    The return annotation is required — it's the schema the docs use.

Generation fails with a `DocError` rather than writing a wrong document when:

- an exception in `raises` isn't registered in the `ErrorHandler` (it would
  really be a `500`);
- an error's status equals the route's success status;
- two different types share a name (schemas are keyed by name);
- the same tag or security scheme is declared twice with different settings;
- two explicit `operation_id`s collide.

### Headers and cookies

Headers and cookies are never DTO fields — a controller reads them off
`Request`. `DocParam` only tells the docs about them:

```python
DocController(
    headers={"X-Request-Id": DocParam(description="Trace id", example="7f3c2a")},
    cookies={"session": DocParam(description="Session, if logged in")},
)
```

## Documenting routers

`DocRouter` sets what every route of a router — and of the routers included
into it — shares:

```python
from heavyswag.doc import DocRouter, DocTag

users = HeavyRouter(
    "/users",
    doc=DocRouter(
        tags=[DocTag("Users", "User management")],
        security=[bearer],
        headers={"X-Request-Id": DocParam(description="Trace id")},
    ),
)
```

`tags`, `headers` and `cookies` add up down the tree (a nearer one with the
same name wins); `security` is taken from the nearest level that sets it.

## Auth

```python
from heavyswag.doc import APIKey, HTTPBasic, HTTPBearer

bearer = HTTPBearer(bearer_format="JWT")  # Authorization: Bearer <token>
basic = HTTPBasic()                       # Authorization: Basic <base64(user:password)>
```

### API keys: header or cookie

`APIKey` takes the name the key travels under, and `location` — where the
client puts it: `"header"` (the default) or `"cookie"`. Spell `location`
out even for a header, so nobody has to remember the default:

=== "Header"

    ```python
    api_key = APIKey("X-Api-Key", location="header", name="apiKeyHeader")
    ```

    The client sends:

    ```shell
    curl -H "X-Api-Key: secret123" http://127.0.0.1:8000/users
    ```

    The controller reads it off `request.headers` (names arrive
    lower-cased):

    ```python
    def require_api_key(request: Request) -> None:
        for name, value in request.headers:
            if name.lower() == "x-api-key" and value == API_KEY:
                return
        raise UnauthorizedError
    ```

=== "Cookie"

    ```python
    api_key = APIKey("api_key", location="cookie", name="apiKeyCookie")
    ```

    The client sends:

    ```shell
    curl -b "api_key=secret123" http://127.0.0.1:8000/users
    ```

    The controller reads it off `request.cookies`:

    ```python
    def require_api_key(request: Request) -> None:
        for name, value in request.cookies:
            if name == "api_key" and value == API_KEY:
                return
        raise UnauthorizedError
    ```

!!! note "No API key in the query string"
    `location="query"` isn't supported — generation fails with a `DocError`.
    A query value is a DTO field (`Query[...]`), declared and validated like
    any other, not something auth adds on the side; and a key in the URL
    ends up in server logs, proxy logs and browser history.

`name=` is the scheme's id in the document (`components.securitySchemes`),
not the key's name on the wire. It defaults to `bearerAuth`, `basicAuth`
and `apiKeyAuth`; two different schemes under one name are a `DocError`,
so give each `APIKey` its own `name` when you use more than one.

### Where `security` comes from

`security=[bearer, api_key]` means *either* of them:

| On the router | On the route | In the docs                      |
| ------------- | ------------ | -------------------------------- |
| `None`        | `None`       | public                           |
| `None`        | `[bearer]`   | needs bearer                     |
| `[bearer]`    | `None`       | needs bearer (inherited)         |
| `[bearer]`    | `()`         | public — explicitly opted out    |
| `[bearer]`    | `[api_key]`  | needs the API key (overridden)   |

!!! danger "`security` documents, it doesn't protect"
    Nothing in `security` checks a single request — that's still your code,
    e.g. a helper the controller calls first:

    ```python
    def require_token(request: Request) -> None:
        for name, value in request.headers:
            if name.lower() == "authorization" and value == f"Bearer {API_TOKEN}":
                return
        raise UnauthorizedError
    ```

    Keep the two in sync: a route with `security` but no check is
    documented as protected while being open.

## Hiding a route

`hidden=True` leaves a route out of the document — together with any tag,
schema or security scheme only it used. The route itself is served as
usual:

```python
@router.get("/internal/metrics", doc=DocController(hidden=True))
```

## The app

```python
from heavyswag.doc import DocApp, DocContact, DocLicense, DocServer

app = HeavySwag(
    main_router=router,
    doc=DocApp(
        title="My API",
        version="1.0.0",
        description="Markdown **welcome** text.",
        contact=DocContact(name="Team", email="team@example.com"),
        license_info=DocLicense(name="MIT"),
        servers=[
            DocServer("http://localhost:8000", "local"),
            DocServer("https://api.example.com", "prod"),
        ],
    ),
)
```

Without `doc=`, the document is titled `HeavySwag API`, version `0.1.0`.

`servers` is optional too. Without it the HTML page's **Попробовать** sends
requests to the server the page itself came from — exactly right when the
app serves its own docs (see [below](#serving-the-page-from-your-app)).
A page opened as a file has no such server: pick «Свой адрес…» there and
type the API's URL.

## OpenAPI 3.1

```python
from heavyswag.doc import build_openapi, generate_swagger_file

generate_swagger_file(app, "openapi.yaml")  # (1)!
spec = build_openapi(app)  # (2)!
```

1.  `.json`, `.yaml` or `.yml` — picked by the extension. YAML is written
    without any extra dependency.
2.  The same document as a plain `dict`.

Both build the route tree first, so every startup check — DTO shapes,
validator settings, documented examples — has passed before a single line is
written.

!!! note "3.1, not 3.0"
    The document is OpenAPI **3.1**: `examples` arrays, `type: [X, "null"]`
    for nullable values. A 3.0-only validator (the classic
    `editor.swagger.io`) reports those as errors — use one that knows 3.1,
    e.g. `editor-next.swagger.io`, or `openapi-spec-validator`.

## The HTML page

```python
from pathlib import Path

from heavyswag.doc import DocUI, generate_docs_html

DOCS_FILE = Path(__file__).with_name("docs.html")  # (1)!
DOCS_UI = DocUI(name="My API", accent="#3b82f6")  # (2)!

generate_docs_html(app, DOCS_FILE, ui=DOCS_UI)
```

1.  Where the page is written. A `Path` next to `main.py` rather than a bare
    `"docs.html"` — that one would land in whatever directory the server
    happens to be started from.
2.  Optional — see [`DocUI`](#docui) below.

One file — styles, scripts and the OpenAPI document all inlined — that opens
straight from disk or can be served by a route. In it:

- every route grouped by tag, with search, plus webhooks and component
  schemas;
- parameters, request and response bodies as expandable schema trees, with
  examples;
- **Попробовать** (try it out): fill in parameters and the body (as JSON or field by
  field), pick a server, send it for real, see the status, headers, timing
  and body — and whether the response matches its documented schema;
- an **Authorize** dialog for every security scheme, applied to the
  routes that need it;
- global headers / cookies sent with every request;
- curl for every request;
- light / dark theme.

### Validation in the browser

The page checks a request against the same schema before sending it — a
missing required field, a value outside `min`/`max`, a string that doesn't
match `pattern`, a wrong enum value, an unknown body key, broken JSON. The
offending input is highlighted with the reason, and **Отправить** (send) stays disabled
until it's fixed. The server checks everything again anyway — the page only
saves a round trip.

What it can't check: the [rules with no JSON Schema keyword](#validators-become-the-schema).
And a missing token is only a warning — sending anyway is how you see the
`401`.

### `DocUI`

| Argument      | Means                                                            |
| ------------- | ---------------------------------------------------------------- |
| `name`        | shown in the top bar; defaults to the API title                  |
| `logo`        | initials / an emoji, or an image URL / `data:` URI               |
| `accent`      | `#rgb` / `#rrggbb` accent color                                  |
| `accent_soft` | second color of the logo gradient; defaults to a lighter accent  |
| `favicon`     | an emoji, or an image URL / `data:` URI                          |

!!! note "Cookies from a page opened as a file"
    A browser never lets a page set the `Cookie` header itself, so cookies
    configured on the page go into curl only. Serve the page from the API's
    own origin (next section) and the browser sends that origin's cookies
    by itself.

## Serving the page from your app

Generate `docs.html` when the app starts, and add a route that sends the
file as-is. `hidden=True` keeps the route out of its own docs; the explicit
`Content-Type` makes the browser render the bytes as a page (see
[Content-Type](index.md#content-type)):

```python
from pathlib import Path

DOCS_FILE = Path(__file__).with_name("docs.html")
DOCS_UI = DocUI(name="My API")


@router.get("/docs", doc=DocController(hidden=True))
async def docs_page(request: Request, _: NoInputDTO) -> Response[bytes]:
    if not has_docs_login(request):  # (1)!
        denied: Response[bytes] = Response(status_code=401)
        denied.attach_header("WWW-Authenticate", 'Basic realm="docs", charset="UTF-8"')
        return denied

    page: Response[bytes] = Response()
    page.set_body(DOCS_FILE.read_bytes())
    page.attach_header("Content-Type", "text/html; charset=utf-8")
    page.attach_header("Cache-Control", "no-store")
    return page


if __name__ == "__main__":
    import uvicorn

    generate_docs_html(app, DOCS_FILE, ui=DOCS_UI)
    uvicorn.run(run_app(app))
```

1.  A bearer token won't do here: a browser following a link never adds
    `Authorization: Bearer …` on its own. HTTP Basic is the one scheme it
    handles itself — a `401` with `WWW-Authenticate: Basic` makes it show a
    login dialog and resend the request with the credentials:

    ```python
    import base64, binascii, hmac

    def has_docs_login(request: Request) -> bool:
        for name, value in request.headers:
            if name.lower() != "authorization":
                continue
            scheme, _, encoded = value.partition(" ")
            if scheme.lower() != "basic":
                return False
            try:
                decoded = base64.b64decode(encoded, validate=True).decode()
            except (binascii.Error, UnicodeDecodeError):
                return False
            user, _, password = decoded.partition(":")
            return hmac.compare_digest(user, DOCS_USER) & hmac.compare_digest(
                password, DOCS_PASSWORD
            )
        return False
    ```

    `hmac.compare_digest` takes the same time however much of the password
    was right, so it can't be guessed character by character. Basic
    credentials are only base64-encoded — serve the page over HTTPS
    anywhere but `localhost`.

### Turning it off in production

The docs route is an ordinary route, so leaving it out is ordinary Python —
register it, and generate the file, only when a flag says so:

```python title="main.py"
import os

DOCS_ENABLED = os.environ.get("DOCS_ENABLED", "0") == "1"

if DOCS_ENABLED:

    @router.get("/docs", doc=DocController(hidden=True))
    async def docs_page(request: Request, _: NoInputDTO) -> Response[bytes]: ...


if __name__ == "__main__":
    import uvicorn

    if DOCS_ENABLED:
        generate_docs_html(app, DOCS_FILE, ui=DOCS_UI)
    uvicorn.run(run_app(app))
```

```shell
DOCS_ENABLED=1 uv run python main.py   # development: /docs is there
uv run python main.py                   # production: /docs is a 404
```

With the flag off the route doesn't exist at all — a `404` like any unknown
path, rather than a page that's merely locked. Default the flag to *off*,
so forgetting to set it in production fails safe.
