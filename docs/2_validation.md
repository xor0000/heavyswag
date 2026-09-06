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

!!! warning "Every declared field is still required"
    Outside of the `Optional`/missing-key rules above, nothing changed: a
    non-optional `Body`/`Query`/path field missing from the request is
    `400 Bad Request` before your controller ever runs.
