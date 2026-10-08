import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from heavyswag.doc import DocApp, DocUI, build_openapi, generate_docs_html
from heavyswag.doc.docs_page import _SCRIPTS, FRONTEND_DIR, _bundle_scripts
from heavyswag.errors import DocError
from heavyswag.routes.application import HeavySwag
from heavyswag.routes.router import HeavyRouter
from heavyswag.specify.request import Request

_DATA_BLOCK = re.compile(
    r'<script type="application/json" id="hs-data">(.*?)</script>', re.DOTALL
)


class _Empty(NamedTuple):
    pass


def _app(doc: DocApp | None = None) -> HeavySwag:
    router = HeavyRouter("/")

    @router.get("/ping")
    async def ping(_: Request, __: _Empty) -> str:
        return "pong"

    return HeavySwag(main_router=router, doc=doc)


def _page(tmp_path: Path, app: HeavySwag, ui: DocUI | None = None) -> str:
    file = tmp_path / "docs.html"
    generate_docs_html(app, file, ui=ui)
    return file.read_text(encoding="utf-8")


def _data(page: str) -> dict[str, Any]:
    (block,) = _DATA_BLOCK.findall(page)
    return json.loads(block)  # type: ignore[no-any-return]


def test_page_embeds_the_openapi_document(tmp_path: Path) -> None:
    app = _app(DocApp(title="Demo", version="1.0"))

    data = _data(_page(tmp_path, app))

    assert data["spec"] == build_openapi(app)


def test_page_embeds_the_ui_settings(tmp_path: Path) -> None:
    ui = DocUI(name="Brand", logo="BR", accent="#3b82f6", favicon="🚀")

    data = _data(_page(tmp_path, _app(), ui))

    assert data["ui"] == {
        "name": "Brand",
        "logo": "BR",
        "accent": "#3b82f6",
        "accent_soft": None,
        "favicon": "🚀",
    }


def test_page_title_is_the_ui_name_or_the_api_title(tmp_path: Path) -> None:
    app = _app(DocApp(title="API <&>", version="1"))

    assert "<title>API &lt;&amp;&gt;</title>" in _page(tmp_path, app)
    assert "<title>Brand</title>" in _page(tmp_path, app, DocUI(name="Brand"))


def test_no_string_in_the_document_can_close_the_data_script(
    tmp_path: Path,
) -> None:
    evil = "</script><script>alert(1)</script><!--"
    app = _app(DocApp(title="Demo", version="1", description=evil))

    page = _page(tmp_path, app)

    assert evil not in page
    assert _data(page)["spec"]["info"]["description"] == evil


@pytest.mark.parametrize(
    "ui",
    [
        DocUI(accent="red"),
        DocUI(accent="#12345"),
        DocUI(accent="#fff;}body{display:none"),
        DocUI(accent_soft="url(x)"),
    ],
)
def test_ui_colors_must_be_hex(tmp_path: Path, ui: DocUI) -> None:
    with pytest.raises(DocError, match="must be a #rgb or #rrggbb color"):
        generate_docs_html(_app(), tmp_path / "docs.html", ui=ui)


def test_every_script_is_bundled() -> None:
    on_disk = {path.name for path in (FRONTEND_DIR / "scripts").glob("*.js")}

    assert set(_SCRIPTS) == on_disk
    assert _SCRIPTS[-1] == "main.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_bundle_is_valid_javascript(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.js"
    bundle.write_text(_bundle_scripts(), encoding="utf-8")

    result = subprocess.run(  # noqa: S603
        [shutil.which("node") or "node", "--check", str(bundle)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
