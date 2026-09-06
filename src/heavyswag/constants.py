from collections.abc import Sequence
from datetime import datetime
from enum import IntEnum
from typing import NamedTuple
from uuid import UUID


class HttpMethod(IntEnum):
    GET = 1
    POST = 2
    PATCH = 3
    PUT = 4
    DELETE = 5
    QUERY = 6


class MethodType(IntEnum):
    CONNECT = 1
    HEAD = 2
    OPTIONS = 3
    TRACE = 4


type Scalar = int | float | str | bool | bytes | UUID | datetime | NamedTuple
type ALLOWED_TYPES = Scalar | Sequence[Scalar] | None
