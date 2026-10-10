import pytest

from heavyswag.doc import DocField
from heavyswag.errors import DocError


def test_doc_field_rejects_empty_examples() -> None:
    with pytest.raises(DocError, match="examples must not be empty"):
        DocField(examples={}).assembly()


def test_doc_field_rejects_example_and_examples_together() -> None:
    with pytest.raises(DocError, match="mutually exclusive"):
        DocField(example="a", examples={"b": "b"}).assembly()


def test_doc_field_examples_in_priority_order() -> None:
    assert DocField(examples={"a": 1, "b": 2}).doc_examples() == (1, 2)
    assert DocField(example=3).doc_examples() == (3,)
    assert DocField(description="no examples").doc_examples() == ()
