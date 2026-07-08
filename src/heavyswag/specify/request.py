from typing import NamedTuple

from heavyswag.http import Method


class Body[Arg](NamedTuple): ...


class Query[Arg](NamedTuple): ...


class Preambule(NamedTuple):
    url: str
    method: Method


class Request(NamedTuple):
    headers: dict[str, str]
    cookies: dict[str, str]
