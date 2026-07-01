install:
    uv sync --all-groups --all-extras

format:
    uv run ruff format
    uv run ruff check