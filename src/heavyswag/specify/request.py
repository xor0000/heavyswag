from typing import NamedTuple

from heavyswag.constants import HttpMethod, MethodType


class Body[Arg](NamedTuple): ...


class Query[Arg](NamedTuple): ...


class Preambule(NamedTuple):
    url: str
    method: HttpMethod | MethodType


class Request(NamedTuple):
    headers: dict[str, str]
    cookies: dict[str, str]
