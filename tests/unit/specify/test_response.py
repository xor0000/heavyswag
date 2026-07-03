from heavyswag.specify.cookie import Cookie
from heavyswag.specify.response import Response


def test_set_cookie() -> None:
    response = Response()

    assert response.cookie is None

    response.set_cookie(Cookie(key="qwerty", value="qwerty_value"))

    assert response.cookie is not None and len(response.cookie) == 1  # noqa: PT018

    response.set_cookie(Cookie(key="qwerty", value="another_value"))
    response.set_cookie(Cookie(key="test_key", value="test_value"))

    assert len(response.cookie) == 2  # noqa: PLR2004


def test_attach_header() -> None:
    response = Response()

    assert response.header is None

    response.attach_header(key="qwerty", value="qwerty_value")

    assert response.header is not None and len(response.header) == 1  # noqa: PT018

    response.attach_header(key="qwerty", value="qwerty_value")
    response.attach_header(key="test_key", value="test_value")

    assert len(response.header) == 2  # noqa: PLR2004


def test_set_body() -> None:
    response = Response()

    assert response.body is None

    response.set_body("any value")
    response.set_body("another")

    assert response.body == "another"
