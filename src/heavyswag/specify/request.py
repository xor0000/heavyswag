from typing import NamedTuple

from heavyswag.constants import HttpMethod, MethodType


class Body[Arg](NamedTuple): ...


class Query[Arg](NamedTuple): ...


class Preambule(NamedTuple):
    url: str
    method: HttpMethod | MethodType


class Request(NamedTuple):
    headers: list[tuple[bytes, bytes]]
    cookies: list[tuple[bytes, bytes]]
