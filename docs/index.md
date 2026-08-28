---
icon: lucide/rocket
---

# Get started

<b>HeavySwag</b> — a disruptor in the world of Python frameworks. Absolutely clean and fresh! :sparkles:

___

## Install

```shell
uv add heavyswag
```

To launch the application, you can install `uvicorn`, `granian`, and other HTTP servers.

## The simplest app

```python title="main.py"
from typing import NamedTuple

from heavyswag import HeavyRouter, HeavySwag, run_app
from heavyswag.specify import Request

router = HeavyRouter("/")

@router.get("/")
async def index(request: Request, dto: tuple[()]) -> str:  # (1)!
    return "Welcome!"


app = HeavySwag(main_router=router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(run_app(app), host="127.0.0.1", port=8000)
```

1.  HeavySwag is a strictly typed framework: every controller must declare an
    input DTO as its 2nd argument, even for routes that take no input at all.
    An empty `Tuple` is the idiomatic "nothing to parse" DTO.

    Every controller has exactly the same shape:

    ```python
    async def controller(request: Request, dto: SomeDTO) -> SomeOutput: ...
    ```

    - the **1st argument** is always `Request` (headers + cookies of the
      incoming request);
    - the **2nd argument** is a DTO — a `NamedTuple` that HeavySwag builds for
      you from the path, the query string and the JSON body (see
      [Request data](#request-data) below);
    - the **return type** can be a plain value (it gets wrapped into a
      `Response` automatically) or a `Response[...]` if you need to control
      status codes, headers or cookies (see [Responses](#responses)).


Run it and hit it:

```shell
uv run python main.py
curl http://127.0.0.1:8000/
```

## Routing

`HeavyRouter` is the only routing primitive. The router you pass to
`HeavySwag(main_router=...)` **must** have `"/"` as its prefix — it's the
root of the whole route tree.

```python
router = HeavyRouter("/")

router.get(path)      # GET
router.post(path)     # POST
router.put(path)      # PUT
router.patch(path)    # PATCH
router.delete(path)   # DELETE
```

### Path parameters

A `{name}` segment in the path becomes a path parameter, matched against the
DTO field with the same name:

```python
@router.get("/items/{item_id}")
async def get_item(request: Request, dto: ItemDTO) -> str: ...
```

Routes are resolved by a compressed radix tree, so **static segments always
win over dynamic ones** at the same depth — `/items/active` will match a
static `/items/active` route before it ever tries `/items/{item_id}`,
regardless of the order you registered them in.

### Nested routers

Group related routes under a prefix and attach them to the main router with
`include_router`:

```python
users_router = HeavyRouter("/users")
main_router.include_router(users_router)

@users_router.get("/{user_id}")
async def get_user(request: Request, dto: UserIdDTO) -> str: ...
# -> GET /users/{user_id}
```

A router prefix must start with `/` and contain only ASCII letters (no
digits, dashes or extra `/` — one path segment per router).

## Request data

DTOs are plain `NamedTuple`s. Every field is resolved according to its
annotation:

| Annotation      | Comes from                                  |
| --------------- | -------------------------------------------- |
| `Body[T]`       | the JSON request body                         |
| `Query[T]`      | the `?query=string`                           |
| anything else    | a path parameter (`{name}` in the route path) |

```python
from typing import NamedTuple
from uuid import UUID

from heavyswag.specify import Body, Query, Request


class UpdateUser(NamedTuple):
    user_id: UUID            # path parameter -> /users/{user_id}
    notify: Query[bool]      # ?notify=true
    age: Body[int]           # {"age": 30, ...} in the JSON body
    tags: Body[list[str]]    # {"tags": ["a", "b"], ...}


@router.patch("/users/{user_id}")
async def update_user(request: Request, dto: UpdateUser) -> str:
    return f"updated {dto.user_id}, age={dto.age}, tags={dto.tags}"
```

```shell
curl -X PATCH "http://127.0.0.1:8000/users/123e4567-e89b-12d3-a456-426614174000?notify=true" \
  -H "Content-Type: application/json" \
  -d '{"age": 30, "tags": ["vip", "new"]}'
```

Supported field types: `str`, `int`, `float`, `bool`, `bytes`, `UUID`,
`datetime`, and `list[T]` for `Body` fields (JSON arrays pass through as-is).

!!! warning "Every declared field is required"
    There's no "optional" marker yet — if a `Body`/`Query` field is declared
    on the DTO and missing from the request, HeavySwag responds `400 Bad
    Request` before your controller ever runs. Design your DTOs (and which
    HTTP verb you use) accordingly — a `PATCH` here means "send every
    updatable field", not "send only what changed".

A malformed value (a non-numeric path segment for an `int` field, a broken
UUID, invalid JSON, ...) also short-circuits to `400 Bad Request` — see
[Error handling](#error-handling) for how to customize this.

## Responses

A controller can simply return a value — it gets wrapped into a `200
Response` for you:

```python
@router.get("/")
async def index(request: Request, dto: tuple[()]) -> str:
    return "Welcome!"
```

Return a `Response[...]` explicitly when you need a specific status code,
extra headers or cookies:

```python
from heavyswag.specify import Response


@router.post("/users")
async def create_user(request: Request, dto: CreateUser) -> Response[str]:
    response: Response[str] = Response(status_code=201)
    response.set_body("created")
    response.attach_header("X-Resource", "user")
    return response
```

## A typical CRUD

A minimal in-memory "users" CRUD, showing path params, query params, the
JSON body and every HTTP verb together:

```python title="users.py"
from typing import NamedTuple
from uuid import UUID, uuid4

from heavyswag import HeavyRouter
from heavyswag.specify import Body, Query, Request, Response

users_router = HeavyRouter("/users")

_DB: dict[UUID, dict[str, str]] = {}


class Empty(NamedTuple): ... # (1)!


class UserId(NamedTuple):
    user_id: UUID


class CreateUser(NamedTuple):
    username: Body[str]
    email: Body[str]


class UpdateUser(NamedTuple):
    user_id: UUID
    username: Body[str]
    email: Body[str]


class ListUsers(NamedTuple):
    search: Query[str]
```


1.  You can also create an empty structure in a similar way.


=== "Create"

    ```python
    @users_router.post("/")
    async def create_user(
        request: Request, dto: CreateUser
    ) -> Response[str]:
        user_id = uuid4()
        _DB[user_id] = {"username": dto.username, "email": dto.email}

        response: Response[str] = Response(status_code=201)
        response.set_body(str(user_id))
        return response
    ```

=== "List"

    ```python
    @users_router.get("/")
    async def list_users(request: Request, dto: ListUsers) -> str:
        matches = [
            f"{uid}: {u['username']}"
            for uid, u in _DB.items()
            if dto.search in u["username"]
        ]
        return "\n".join(matches) or "no users"
    ```

=== "Get one"

    ```python
    @users_router.get("/{user_id}")
    async def get_user(request: Request, dto: UserId) -> Response[str]:
        user = _DB.get(dto.user_id)
        if user is None:
            response: Response[str] = Response(status_code=404)
            response.set_body("not found")
            return response

        response = Response()
        response.set_body(f"{user['username']} <{user['email']}>")
        return response
    ```

=== "Update"

    ```python
    @users_router.patch("/{user_id}")
    async def update_user(request: Request, dto: UpdateUser) -> str:
        _DB[dto.user_id] = {"username": dto.username, "email": dto.email}
        return "updated"
    ```

=== "Delete"

    ```python
    @users_router.delete("/{user_id}")
    async def delete_user(request: Request, dto: UserId) -> str:
        _DB.pop(dto.user_id, None)
        return "deleted"
    ```

Wire it up:

```python title="main.py"
from heavyswag import HeavyRouter, HeavySwag, run_app

from users import users_router

main_router = HeavyRouter("/")
main_router.include_router(users_router)

app = HeavySwag(main_router=main_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(run_app(app), host="127.0.0.1", port=8000)
```

```shell
curl -X POST http://127.0.0.1:8000/users \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com"}'

curl "http://127.0.0.1:8000/users?search=ali"
curl http://127.0.0.1:8000/users/<user_id>

curl -X PATCH http://127.0.0.1:8000/users/<user_id> \
  -H "Content-Type: application/json" \
  -d '{"username": "alice2", "email": "alice2@example.com"}'

curl -X DELETE http://127.0.0.1:8000/users/<user_id>
```

## Error handling

Every unhandled exception is caught before it reaches the ASGI boundary and
turned into a `Response` by an `ErrorHandler`. By default:

- any `HeavySwagError` (and its subclasses, e.g. `SerializationError`) maps
  to a sensible status code;
- anything else falls back to `500 Internal Server Error`.

Register your own exception → `(status_code, message)` mapping:

```python
from heavyswag.errors import HeavySwagError
from heavyswag.middlewares import ErrorHandler


class OutOfStockError(HeavySwagError):
    pass


err_handler = ErrorHandler(
    map_errors={OutOfStockError: (409, "Out of Stock")},
)

app = HeavySwag(main_router=main_router, err_handler=err_handler)
```

```python
@router.get("/widgets/broken")
async def broken_widget(request: Request, dto: Empty) -> str:
    raise OutOfStockError("widget 'broken' is out of stock")
```

The lookup walks the exception's MRO, so registering a base class also
covers every subclass you didn't map explicitly — you don't need an entry
for every single exception type, just the ones whose status code matters.

## Middlewares

A middleware is anything shaped like:

```python
async def middleware(call_next: CallNext, context: RequestContext) -> Response[Any]:
    # do something before
    response = await call_next(context)
    # do something after
    return response
```

— a plain function or a class with `__call__` of that shape; no base class
to inherit from.

`HeavySwag` always runs three middlewares even if you don't ask for them:
CORS, error handling (see above) and request logging. Pass your own
instances in `middlewares=[...]` to replace the defaults, and anything else
you add runs closer to your controllers, after those three:

```python
from heavyswag import HeavySwag
from heavyswag.middlewares import CORSMiddleware
from heavyswag.middlewares import LoggingMiddleware

app = HeavySwag(
    main_router=main_router,
    middlewares=[
        CORSMiddleware(
            allow_origins=["https://example.com"],
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_credentials=True,
        ),
        LoggingMiddleware(),
    ],
)
```

### Writing your own

```python
from typing import Any

from heavyswag.middlewares import CallNext, RequestContext
from heavyswag.specify import Response


class ApiKeyMiddleware:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def __call__(
        self, call_next: CallNext, context: RequestContext
    ) -> Response[Any]:
        if context.preambule.url.startswith("/admin"):
            if context.request.headers.get("x-api-key") != self._api_key:
                response: Response[str] = Response(status_code=401)
                response.set_body("Unauthorized")
                return response

        return await call_next(context)
```

```python
app = HeavySwag(
    main_router=main_router,
    middlewares=[ApiKeyMiddleware("secret123")],
)
```

`RequestContext` gives you `.preambule` (method + url + query string),
`.request` (headers + cookies) and `.serializer` (the low-level request/
response converter, rarely needed directly).

## Cookies

Read them from the request, set them on the response:

```python
from heavyswag.specify import Cookie, Request, Response


@router.post("/login")
async def login(request: Request, dto: Empty) -> Response[str]:
    return Response(  # (1)!
        cookie={
            Cookie(key="session_id", value="abc123", http_only=True, max_age=3600),
        },
        body="logged in",
    )


@router.get("/profile")
async def profile(request: Request, dto: Empty) -> str:
    session_id = request.cookies.get("session_id")
    return f"session: {session_id}" if session_id else "not logged in"
```

1. or initialize the response and then populate it
```python
response: Response[str] = Response()
response.set_body("logged in")
response.set_cookie(
    Cookie(key="session_id", value="abc123", http_only=True, max_age=3600)
)
return response
```

`Cookie` defaults to `path="/"`, `http_only=True` and `same_site=Lax` —
override any of them per cookie.

## Lifespan

`lifespan` runs setup code once before the server starts accepting requests,
and teardown code once after it stops accepting them — the `yield` is the
point where the app is "up" and serving traffic:

```python
async def lifespan(app: HeavySwag) -> AsyncIterator[None]:
    ...  # runs once, before the first request
    yield
    ...  # runs once, after the last request
```

This is the right place for anything expensive or stateful that a request
handler shouldn't repeat on every call: loading an ML model into memory,
opening a database connection pool, warming up a shared HTTP client,
starting a background task, or resolving a dependency from a DI container.
On the way out, it's where you release exactly those things — close
connections, flush buffers, cancel background tasks.

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from heavyswag import HeavySwag

import jobs.send_event_to_kafka as task


@asynccontextmanager
async def lifespan(app: HeavySwag) -> AsyncIterator[None]:
    await task.run()

    yield

    await task.completion()



app = HeavySwag(main_router=main_router, lifespan=lifespan)
```

**Graceful shutdown.** An ASGI server only sends `lifespan.shutdown` after
it has stopped accepting new connections, which is exactly why the code
after `yield` is the right place to wind things down cleanly instead of
having them killed mid-flight: `await`, don't just cancel, anything still in
progress — a background task (`task.completion()` above), in-flight writes,
open connections — before the process actually exits.

`lifespan` is optional — a no-op default is used if you don't pass one.

## Running

```shell
uv run python main.py
```

If you'd rather drive `uvicorn` from the CLI (e.g. for `--reload` during
development), expose the ASGI callable as a module-level attribute and point
`uvicorn` at it:

```python title="main.py"
asgi_app = run_app(app)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(asgi_app, host="127.0.0.1", port=8000)
```

```shell
uv run uvicorn main:asgi_app --reload
```
