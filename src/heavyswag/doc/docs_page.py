import html
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from heavyswag.doc.generators import build_openapi
from heavyswag.doc.models import DocUI
from heavyswag.errors import DocError

if TYPE_CHECKING:
    from heavyswag.routes.application import HeavySwag

FRONTEND_DIR = Path(__file__).parent / "frontend"

# Inlined in this order into one `<script>`, wrapped in a single
# function scope: a later file may call anything an earlier one
# declares, and nothing leaks onto `window`. Only `main.js` runs code
# at load time.
_SCRIPTS = (
    "utils.js",
    "markdown.js",
    "spec.js",
    "schema_view.js",
    "change_theme.js",
    "set_barier.js",
    "send_request.js",
    "render.js",
    "main.js",
)
_STYLES = ("dark_theme.css", "light_theme.css", "main.css")

_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def generate_docs_html(
    app: "HeavySwag",
    file: str | Path,
    ui: DocUI | None = None,
) -> None:
    """Write a self-contained interactive documentation page for `app`
    to `file` — styles, scripts and the OpenAPI document all inlined,
    so it opens straight from disk, or can be served as-is by a route.
    """
    Path(file).write_text(_render_page(app, ui), encoding="utf-8")


def _render_page(app: "HeavySwag", ui: DocUI | None) -> str:
    ui = ui or DocUI()
    _validate_ui(ui)

    spec = build_openapi(app)
    title = ui.name or spec["info"]["title"]
    data = {"ui": ui._asdict(), "spec": spec}

    template = _read("index.html")
    values = {
        "title": html.escape(title),
        "styles": "\n".join(_read("styles", name) for name in _STYLES),
        "scripts": _bundle_scripts(),
        "data": _json_for_script(data),
    }
    return _PLACEHOLDER.sub(lambda match: values[match.group(1)], template)


def _validate_ui(ui: DocUI) -> None:
    # Both colors end up in a CSS custom property — anything but a
    # plain hex color is refused rather than escaped.
    for name in ("accent", "accent_soft"):
        color = getattr(ui, name)
        if color is not None and not _HEX_COLOR.match(color):
            msg = f"DocUI.{name} must be a #rgb or #rrggbb color, got {color!r}."
            raise DocError(msg)


def _bundle_scripts() -> str:
    parts = [f"// ---- {name}\n{_read('scripts', name)}" for name in _SCRIPTS]
    body = "\n".join(parts)
    return f'(() => {{\n"use strict";\n{body}\n}})();'


def _json_for_script(value: Any) -> str:  # noqa: ANN401
    """JSON safe to inline into a `<script type="application/json">`:
    `<`, `>` and `&` are escaped so no string in the document can
    close the tag (`</script>`) or open a comment."""
    text = json.dumps(value, ensure_ascii=False)
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def _read(*parts: str) -> str:
    return FRONTEND_DIR.joinpath(*parts).read_text(encoding="utf-8")
