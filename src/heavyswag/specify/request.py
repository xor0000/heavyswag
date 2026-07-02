from typing import NamedTuple


class Body[Arg](NamedTuple): ...

class Query[Arg](NamedTuple): ...


class Request(NamedTuple):
    headers: dict[str, str]
    cookies: dict[str, str]
