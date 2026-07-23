install:
    uv sync --all-groups --all-extras

lint:
    uv run ruff format
    uv run ruff check
    uv run mypy .

test:
    uv run pytest .
