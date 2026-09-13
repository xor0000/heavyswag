---
icon: lucide/shield-check
---

# Validation

A DTO field is resolved from one of three sources, based on its annotation:

| Annotation   | Comes from                                   |
| ------------ | --------------------------------------------- |
| `Body[T]`    | the JSON request body                         |
| `Query[T]`   | the `?query=string`                           |
| anything else | a path parameter (`{name}` in the route path) |

Two kinds of checks apply on top of that:

- **Shape checks** run once, when the app starts — while `HeavySwag` builds the
  radix tree out of your routes. A DTO that breaks these rules never serves a
  single request; it raises `RouteTreeError` at startup.
- **Value checks** run per-request, while HeavySwag builds the DTO from the
  incoming request. A DTO that's shaped correctly but received bad input
  raises `SerializationError`, which the default `ErrorHandler` turns into
  `400 Bad Request`.

## Empty DTOs

A controller that takes no input at all still has to declare a DTO. The
portable way to spell "nothing to parse" is an empty `NamedTuple`:

```python
class Empty(NamedTuple): ...


@router.get("/")
async def index(request: Request, dto: Empty) -> str:
    return "Welcome!"
```

!!! warning "`tuple[()]` only works on Python 3.14+"
    `tuple[()]` as a DTO requires Python 3.14. On 3.12 and 3.13,
    `typing.get_type_hints(tuple[()])` raises `TypeError: tuple[()] is not
    a module, class, method, or function`, so the route dies while
    `HeavySwag` builds the radix tree — at startup, before it serves a
    single request.

    An empty `NamedTuple` behaves identically on every supported version and
    keeps the shape checks honest.

## No default values

A DTO field must never declare a default:

```python
class Bad(NamedTuple):
    value: Body[str] | None = None  # (1)!
```

1.  Rejected at startup with `RouteTreeError: DTO 'Bad' must not declare
    default values for: value.`

The wire format already has an explicit way to say "no value": an absent key
(bad request) or, for optional fields, an explicit JSON `null`. A `NamedTuple`
default would let a field silently fall back without the client ever sending
anything, which bypasses that contract and hides bugs where a client simply
forgot a field. Always write:

```python
class Good(NamedTuple):
    value: Body[str] | None
```

## Optional fields

Only `Body[T]` and `Query[T]` fields may be `Optional` (`T | None`). A path
parameter never can be:

```python
class Bad(NamedTuple):
    item_id: str | None  # (1)!


@router.get("/items/{item_id}")
async def get_item(request: Request, dto: Bad) -> str: ...
```

1.  Rejected at startup with `RouteTreeError: DTO 'Bad' field 'item_id' is a
    path parameter and must not be Optional.`

A matched route always has a value for every `{name}` segment in its path —
there's no way for a path parameter to be "absent" — so `Optional` there
would be a type that lies about what can actually happen.

### `Body[T] | None`

- An **explicit JSON `null`** resolves to `None`:

    ```json
    {"value": null}
    ```

- A **missing key** is still `400 Bad Request` — `Optional` only means "this
  key may hold `null`", not "this key may be omitted":

    ```json
    {}
    ```

### `Query[T] | None`

Query strings have no `null` of their own, so the rule is different: a
**missing key** resolves to `None`, no error:

```
GET /search            -> dto.q is None
GET /search?q=cats     -> dto.q == "cats"
```

There's no convention for an "explicit null" in a query string (`?q=null` is
just the four-character string `"null"`, not a null value) — don't invent
one on the client.

## Query values

A query string is flat text after `?`, split into `name=value` pairs — it has
no notion of a data type. Per [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986),
a value should never be wrapped in quotes: `"` isn't in the `unreserved` or
`reserved` character sets, so a literal one must be percent-encoded (`%22`)
to appear in a URL at all. Concretely:

```
?age=30       -> Query[int]  coerces to 30
?age="30"     -> Query[int]  fails to parse '"30"' as int
```

`Query[T]` supports the same scalars as everything else — `str`, `int`,
`float`, `bool`, `UUID`, `datetime`, `bytes` — parsed from that single string.

### Repeated keys

A key repeated in the query string (`?tag=a&tag=b`) collects into a
`Query[list[T]]` field, each item coerced to `T`:

```python
class Search(NamedTuple):
    tags: Query[list[str]]
    ids: Query[list[int]]
```

```
?tags=a&tags=b        -> dto.tags == ["a", "b"]
?ids=1&ids=2&ids=3    -> dto.ids == [1, 2, 3]
```

A **non-list** `Query[T]` field has no sane value to pick if the same key
shows up more than once, so that's a bad request rather than silently
keeping the first or last one:

```
?flag=true&flag=false   -> 400 Bad Request for `flag: Query[bool]`
```

`Optional` and repeated keys compose normally: `Query[list[T]] | None`
resolves to `None` when the key is absent, and to a list (with as many items
as the key was repeated) when it's present at least once.

## Path parameters

Path segments are always a single raw string, exactly like an individual
query value, so they support the same scalars — `str`, `int`, `float`,
`bool`, `UUID`, `datetime`, `bytes`:

```python
class GetEvent(NamedTuple):
    event_id: UUID
    created_at: datetime


@router.get("/events/{event_id}/{created_at}")
async def get_event(request: Request, dto: GetEvent) -> str: ...
```

They just can't be `Optional` (see above) and can't be a `list[T]` — a path
segment is one value, and there's no repeated-key mechanism for a URL path
the way there is for a query string.

### Path fields and `{name}` segments must match

A DTO's path (bare) fields and the route's own `{name}` segments are
checked against each other at startup, in both directions:

- A path field with no matching segment in the route can never be
  resolved:

    ```python
    class Bad(NamedTuple):
        value: str  # (1)!


    @router.post("/")
    async def create(request: Request, dto: Bad) -> None: ...
    ```

    1.  Rejected at startup with `RouteTreeError: DTO 'Bad' field 'value' is
        a path parameter, but '/' has no '{value}' segment.`

- A `{name}` segment with no matching field is a value the route accepts
  but no DTO field ever reads:

    ```python
    class Empty(NamedTuple): ...


    @router.post("/{value}")
    async def create(request: Request, dto: Empty) -> None: ...  # (1)!
    ```

    1.  Rejected at startup with `RouteTreeError: Path '/{value}' declares
        path parameter '{value}', but DTO 'Empty' has no matching field.`

## Nested bodies

A `Body[T]` field's `T` doesn't have to be a scalar — it can be another
`NamedTuple`, letting a JSON body nest arbitrarily deep. Its own fields
don't need markers — a nested `NamedTuple`, unlike a top-level DTO, has no
path or query string to tell a bare field apart from a `Body[...]` one, so
a plain type is enough:

```python
class Address(NamedTuple):
    city: str
    zip_code: str


class CreateUser(NamedTuple):
    name: Body[str]
    address: Body[Address]


@router.post("/users")
async def create_user(request: Request, dto: CreateUser) -> str: ...
```

```json
{"name": "Max", "address": {"city": "Berlin", "zip_code": "10115"}}
```

`serialize_dto` unwraps `Address` from the nested JSON object the same way
it resolves a top-level `Body` field — recursively, so nesting can go as
deep as you want. If the value at that key isn't a JSON object at all (a
string, a number, `[1, 2]`, ...), that's a `400 Bad Request` at request
time, not something the checks below could have caught up front.

`Body[T]` also works on `Address`'s own fields — it's accepted, just
redundant there:

```python
class Address(NamedTuple):
    city: Body[str]
    zip_code: Body[str]
```

### Only `NamedTuple` nests, and only without `Query`

Two shape checks keep nesting from silently doing something a JSON object
can't — both run once, at startup:

- The target of a nested `Body[T]` must be a `NamedTuple`. A `dataclass` or
  any other class is rejected:

    ```python
    @dataclass
    class Address:
        city: str


    class Bad(NamedTuple):
        address: Body[Address]  # (1)!
    ```

    1.  Rejected at startup with `RouteTreeError: DTO 'Bad' field 'address'
        nests 'Address', which must be a NamedTuple.`

- Nothing in that nested `NamedTuple` may be `Query[...]`, all the way
  down — there's no query string inside a JSON object to resolve it from:

    ```python
    class Address(NamedTuple):
        city: Body[str]
        zip_code: Query[str]  # (1)!


    class Bad(NamedTuple):
        address: Body[Address]
    ```

    1.  Rejected at startup with `RouteTreeError: DTO 'Bad' field 'address'
        nests 'Address', which must not use Query fields — there's no
        query string inside a JSON body. A bare field or Body[X] are both
        fine.`

    `Address` is still perfectly valid on its own, as a top-level
    (controller-facing) DTO — this rule only kicks in once it's nested
    inside another DTO's `Body[...]` field.

!!! tip "A bare field is fine inside a nested `Body`"
    Unlike a top-level DTO, a nested one has no path or query string to
    tell a bare field apart from a `Body[...]` one — both are just read
    straight off the same JSON object:

    ```python
    class Address(NamedTuple):
        city: Body[str]
        zip_code: str  # no marker, and that's fine here
    ```

    This isn't just permitted, it's what makes
    [reusing a request DTO as a nested response DTO](#response-dtos)
    possible without writing a second, marker-free copy of the same shape.

A path or query field can't be a `NamedTuple` either, nested or not — a URL
path segment or a query value is always a single flat string:

```python
class Address(NamedTuple):
    city: Body[str]


class Bad(NamedTuple):
    address: Address  # (1)!
```

1.  Rejected at startup with `RouteTreeError: DTO 'Bad' field 'address' is
    a path parameter and must not be a NamedTuple.` (`query parameter` for
    `Query[Address]`.)

### `Body`/`Query` need a type parameter

`Body` and `Query` are generic — writing one bare, without `[X]`, leaves
the field's target as the marker's own unbound type variable, which
`Serializer` could never turn a value into:

```python
class Bad(NamedTuple):
    value: Body  # (1)!
```

1.  Rejected at startup with `RouteTreeError: DTO 'Bad' field 'value' uses
    'Body' without a type parameter — write 'Body[X]' instead.`

This is caught wherever it appears, including inside a nested
`Body[NamedTuple]` target.

## Response DTOs

The type a controller *returns* — bare, or wrapped in `Response[...]` —
follows a different rule than the input DTO above: it's always serialized
whole into the response body, so there's no source to pick between. The
usual, recommended shape is a plain, unmarked type:

```python
class UserOut(NamedTuple):
    id: UUID
    name: str


@router.get("/users/{user_id}")
async def get_user(request: Request, dto: UserId) -> UserOut: ...
```

`Body[T]` is also allowed on a response type — it's redundant there (a bare
field and a `Body[T]` field serialize identically), but not rejected:

```python
class UserOut(NamedTuple):
    id: Body[UUID]  # redundant, not wrong
    name: str
```

!!! tip "Why allow a redundant marker at all?"
    So a `NamedTuple` already used as a request DTO — `Body[...]` markers
    and all — can be reused, unchanged, as a nested field of a response
    DTO. No need to strip its markers just because it's now on the way
    out:

    ```python
    class Address(NamedTuple):
        city: Body[str]
        zip_code: Body[str]


    class UserOut(NamedTuple):
        id: UUID
        address: Address  # the same Address, reused as a nested response field


    @router.post("/users")
    async def create_user(request: Request, dto: Address) -> UserOut:
        return UserOut(id=uuid4(), address=dto)
    ```

    `Address` keeps its `Body[...]` markers in both roles — nothing needs
    to change about it to go from a request DTO to a nested response
    field.

    This isn't the recommended default — a dedicated, marker-free type for
    `Address` is clearer about what actually goes out on the wire — but
    it's a valid shortcut when the request and response shapes are
    genuinely the same, and you'd rather not maintain two identical
    `NamedTuple`s.

`Query[T]` is the one marker that's never allowed on a response type,
nested or not — a response has no query string to resolve it from:

```python
class Bad(NamedTuple):
    id: Query[UUID]  # (1)!
    name: str


@router.get("/users/{user_id}")
async def get_user(request: Request, dto: UserId) -> Bad: ...
```

1.  Rejected at startup with `RouteTreeError: DTO 'Bad' field 'id' has a
    Query marker, but a response has no query string to resolve it from —
    use a bare field or Body[X] instead.`

The check follows nesting too — a `Query[...]` field buried inside an
otherwise unmarked nested `NamedTuple` field is still caught, because that
nested value ends up in the same response body:

```python
class Details(NamedTuple):
    zip_code: Query[str]  # (1)!


class Bad(NamedTuple):
    details: Details
```

1.  `Bad` is rejected at startup for the same reason, even though `details`
    itself carries no marker — the `Query[...]` only has to exist
    *somewhere* in the nested shape.

`Response[T]` is unwrapped before this check runs, so it always validates
`T` — never `Response` itself.
