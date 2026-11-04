from heavyswag.specify.cookie import Cookie
from heavyswag.specify.response import Response


def test_set_cookie() -> None:
    response = Response[None]()

    assert response.cookies is None

    response.set_cookie(Cookie(key="qwerty", value="qwerty_value"))

    assert response.cookies is not None and len(response.cookies) == 1  # noqa: PT018

    response.set_cookie(Cookie(key="qwerty", value="another_value"))
    response.set_cookie(Cookie(key="test_key", value="test_value"))

    assert len(response.cookies) == 2  # noqa: PLR2004


def test_attach_header() -> None:
    response = Response[None]()

    assert response.headers is None

    response.attach_header(key="qwerty", value="qwerty_value")

    assert response.headers is not None and len(response.headers) == 1  # noqa: PT018

    response.attach_header(key="qwerty", value="qwerty_value")
    response.attach_header(key="test_key", value="test_value")

    assert len(response.headers) == 2  # noqa: PLR2004


def test_set_content() -> None:
    response = Response[str]()

    assert response.content is None

    response.content = "any value"
    response.content = "another"

    assert response.content == "another"
