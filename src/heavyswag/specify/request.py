from typing import Any, NamedTuple

from heavyswag.http import Method


class Body[Arg](NamedTuple): ...


class Query[Arg](NamedTuple): ...


class Request(NamedTuple):
    url: str
    method: Method
    body: dict[str, Any]
    headers: dict[str, str]
    cookies: dict[str, str]
