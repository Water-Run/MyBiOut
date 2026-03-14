"""MyBiOut! FastAPI 应用与路由定义"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

_PAGES_DIR = Path(__file__).resolve().parent
_ASSETS_DIR = _PAGES_DIR.parent / "assets"

app = FastAPI(title="MyBiOut!", version="0.1.0")

app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """主页"""
    html_file = _PAGES_DIR / "index.html"
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"))