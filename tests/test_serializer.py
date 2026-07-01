from heavyswag.internal._serializer import Serializer

def test_serialize_python_list() -> None:
    assert Serializer.serialize_py(list(range(10))) == b"[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]"

def test_serialize_python_tuple() -> None:
    assert Serializer.serialize_py(tuple(range(10))) == b"[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]"