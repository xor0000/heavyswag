from typing import Annotated, ClassVar, NamedTuple, TypeVar

from heavyswag.constants import HttpMethod, MethodType


class Marker:
    __slots__ = ()
    name: ClassVar[str]

    def __repr__(self) -> str:
        return f"<Marker {self.name!r}>"


class QueryMarker(Marker):
    name = "query"


class BodyMarker(Marker):
    name = "body"


_MarkerValueT = TypeVar("_MarkerValueT")
Query = Annotated[_MarkerValueT, QueryMarker()]
Body = Annotated[_MarkerValueT, BodyMarker()]


class Preambule(NamedTuple):
    url: str
    method: HttpMethod | MethodType
    query: str = ""


class Request(NamedTuple):
    headers: list[tuple[str, str]]
    cookies: list[tuple[str, str]]
