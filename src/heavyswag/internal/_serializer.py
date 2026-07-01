from collections.abc import Sequence
from typing import Any

from heavyswag.exceptions import SwagException

class Serializer:
    @classmethod
    def serialize_json(cls, message: bytes) -> Any:
        ...

    @classmethod
    def serialize_py(cls, object: Any) -> bytes:
        if isinstance(object, Sequence):
            return f"[{', '.join(map(str, object))}]".encode()

        raise SwagException(f"Undefined serialize strategy for {type(object)}")