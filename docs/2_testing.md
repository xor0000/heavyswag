---
icon: lucide/flask-conical
---

# Testing

## Install and import

```shell
uv add --dev pytest pytest-asyncio
```

```python
from heavyswag import run_test

app = HeavySwag(main_router=router)
client = run_test(app) # (1)!
```

1.  Talks to `app` directly, in-process, over [`httpx.ASGITransport`](https://www.python-httpx.org/async/) — no
    socket, no running server, no `uvicorn`.
```python 
client = run_test(app, base_url="http://test.example.com")
```
`base_url` defaults to `"http://test"`; override it if a controller
    cares about the host (absolute-URL generation, `Host` header checks,
    ...).

## A pytest fixture

```python title="conftest.py"
from httpx import AsyncClient

import pytest
from heavyswag import run_test

from my_service.delivery import app  # HeavySwag app


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    async with run_test(app) as test_client:
        yield test_client
```

## Testing the CRUD example

Against the `users_router` from [A typical CRUD](index.md#a-typical-crud),
wired into `app` in `main.py`:

```python title="test_users.py"
@pytest.mark.asyncio
async def test_create_then_get_user(client: AsyncClient) -> None:
    response = await client.post(
        "/users",
        json={"username": "pistachio17.2", "email": "pistachio@example.com"},
    )
    assert = response.status_code == 201
    user_id = response.text  # the CRUD example returns the id as-is

    check_response = await client.get(f"/users/{user_id}")
    assert check_response.status_code == 200
    assert "pistachio17.2" in check_response.text


@pytest.mark.asyncio
async def test_get_missing_user_returns_404(client: AsyncClient) -> None:
    response = await client.get("/users/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
```

!!! tip "Fresh state per test"
    Monitor the state of your data to avoid unexpected behavior.
