---
icon: lucide/shield-check
---

# Validation

[Serialization](2_validation.md) only decides *where* a DTO field's value
comes from and coerces it to the right Python type. It says nothing about
whether that value actually makes sense — a `Body[str]` field happily
accepts `""` or a 10,000-character string unless something narrows it down.
That's what a **validator** does: an extra piece of `Annotated` metadata,
right alongside the wire marker, that describes rules for a single field.

```python
username: Annotated[
    Body[str],
    StrField(max_len=13, min_len=3, pattern=r"^[a-z0-9_]+$"),
]
```

A validator is a plain `NamedTuple` — `StrField` is the first one, more
follow the same shape (`IntField`, `EmailField`, ...). Every validator
exposes the same two methods, and nothing in the framework needs to know
which concrete type it's dealing with — it just checks whether the object
has the method:

```python
class SomeField(NamedTuple):
    ...

    def assembly(self) -> None: ...
    def validate(self, value: T) -> None: ...
```

## Two phases

| Phase | Runs | Checks | On failure |
| --- | --- | --- | --- |
| **Assembly** | once, while `HeavySwag` builds the radix tree | the validator's own settings, for internal contradictions | `ValidationError` at startup |
| **Runtime** | once per request, after `Serializer` coerces the value | the actual value the client sent | `ValidationError` → `400 Bad Request` |

### Assembly

`CompressedRadixTree._insert` calls `assembly()` on every field's
validator(s) right after the [shape checks](2_validation.md), before the
route is ever reachable:

```python
username: Annotated[Body[str], StrField(min_len=10, max_len=3)]  # (1)!
```

1.  Rejected at startup with `ValidationError: max_len must be greater than
    or equal to min_len.` — this is a mistake in the DTO itself, not
    something any request could ever trigger, so it's caught the same way
    a broken route path is: before the app serves a single request.

`assembly()` never sees a value — it can only reason about the rule
configuration itself: conflicting flags (`is_upper` and `is_lower` both
`True`), an unparsable `pattern`, out-of-range bounds, and so on.

### Runtime

`Serializer.serialize_dto` calls `validate(value)` on every field's
validator(s), right after coercing that field's value — recursively, so a
validator on a nested `Body[NamedTuple]` field or on each item of a
`Query[list[T]]` field runs the same way:

```python
username: Annotated[Body[str], StrField(min_len=3)]
```

```json
{"username": "ab"}
```

Rejected with `ValidationError: String length is less than 3.`, which the
default `ErrorHandler` turns into `400 Bad Request` — the same bucket as a
`SerializationError`, since both mean "the client sent something this
route can't accept."

A `None` value (an absent `Optional` field) skips validation entirely —
there's nothing to check a rule against.

## `StrField`

```python
from heavyswag.validation import StrField
```

`StrField` covers everything about a single string value: length, casing,
character composition, and pattern matching. Every field defaults to
`None`, meaning "no opinion" — only the constraints you set are enforced.

### Length

| Field | Meaning |
| --- | --- |
| `min_len: int` | minimum length, inclusive |
| `max_len: int` | maximum length, inclusive |

```python
StrField(min_len=3, max_len=13)
```

Both must be non-negative, and `max_len` must be greater than or equal to
`min_len` — checked at assembly.

### Pattern

| Field | Meaning |
| --- | --- |
| `pattern: str` | a regex the value must fully match |
| `pattern_preset: Literal[...]` | a built-in regex instead of a hand-written one |

```python
StrField(pattern=r"^[a-z0-9_]+$")
StrField(pattern_preset="email")
```

`pattern` is checked with `re.fullmatch` — the whole value has to match,
not just a substring. `pattern_preset` picks one of:

| Preset | Matches |
| --- | --- |
| `"email"` | `local@domain.tld` |
| `"url"` | `http://...` / `https://...` |
| `"credit_card"` | 13–19 digits |
| `"phone"` | an optional leading `+` and 7–15 digits |
| `"slug"` | lowercase, digits, single hyphens between words |
| `"password"` | 8+ non-whitespace characters with at least one lowercase, one uppercase, and one digit |

A `pattern_preset` fully describes the validation on its own — set it
*without* any other `StrField` field, `pattern` included:

```python
StrField(pattern_preset="email", min_len=5)  # (1)!
```

1.  Rejected at startup with `ValidationError: pattern_preset must be set
    without any other StrField fields.`

### Case

| Field | Meaning | Example |
| --- | --- | --- |
| `first_is_upper: bool` | first character is uppercase | `"David"` → `True` |
| `first_is_lover: bool` | first character is lowercase | `"david"` → `True` |
| `is_upper: bool` | the whole string is uppercase | `"RUB"` → `True` |
| `is_lower: bool` | the whole string is lowercase | `"rub"` → `True` |
| `has_uppercase: bool` | contains at least one uppercase character | `"Password1"` → `True` |
| `has_lowercase: bool` | contains at least one lowercase character | `"Password1"` → `True` |

`first_is_upper` and `first_is_lover` can't both be `True`, neither can
`is_upper` and `is_lower`, and `is_upper=True` conflicts with
`has_lowercase=True` (and symmetrically for `is_lower`/`has_uppercase`) —
all checked at assembly, since no value could ever satisfy them together.

### Digits and special symbols

| Field | Meaning |
| --- | --- |
| `has_digits: bool` | `True` requires at least one digit, `False` forbids any |
| `has_special_symbols: bool` | same, for punctuation characters |
| `min_special_symbols: int` | minimum number of punctuation characters |

```python
StrField(has_digits=True, min_special_symbols=1)  # "Passw0rd!"
```

`has_special_symbols=False` conflicts with a `min_special_symbols` above
zero — both checked at assembly.

### Whitespace

| Field | Meaning |
| --- | --- |
| `has_whitespace: bool` | `True` requires whitespace, `False` forbids any |
| `strip_whitespace: bool` | strip leading/trailing whitespace *before* every other check |
| `no_leading_trailing_whitespace: bool` | reject leading/trailing whitespace instead of stripping it |

`strip_whitespace` only affects what the other rules see during
`validate()` — it does not change the value stored on the DTO.

### Repeats and character set

| Field | Meaning | Example |
| --- | --- | --- |
| `no_consecutive_repeats: int` | reject N or more identical characters in a row | `no_consecutive_repeats=2` rejects `"aab"` |
| `is_alpha: bool` | letters only | `"John"` → `True` |
| `is_alnum: bool` | letters and digits only | `"John1"` → `True` |
| `is_ascii: bool` | ASCII characters only | `"John"` → `True`, `"Джон"` → `False` |

`no_consecutive_repeats` must be at least 2 — below that, it would reject
every non-empty string. `is_alpha=True` conflicts with `has_digits=True`
and with `has_special_symbols=True`, for the same reason.

### `char_list`

```python
char_list: tuple[bool, str]
```

An allowlist or a denylist of characters, chosen by the first element:

```python
StrField(char_list=(True, "qwerty"))    # only these characters are allowed
StrField(char_list=(False, "!@#$>ls"))  # these characters are forbidden
```

The character set must not be empty — checked at assembly.
