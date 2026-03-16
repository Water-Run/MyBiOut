"""MyBiOut! FastAPI 应用与路由定义"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

_PAGES_DIR = Path(__file__).resolve().parent
_ASSETS_DIR = _PAGES_DIR.parent / "assets"

app = FastAPI(title="MyBiOut!", version="0.1.0")

app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")


# ======================= 页面 =======================


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """主页"""
    return HTMLResponse(
        (_PAGES_DIR / "index.html").read_text(encoding="utf-8")
    )


@app.get("/ohmyconfig", response_class=HTMLResponse)
async def ohmyconfig_page() -> HTMLResponse:
    """设置页"""
    return HTMLResponse(
        (_PAGES_DIR / "ohmyconfig" / "ohmyconfig.html").read_text(encoding="utf-8")
    )


# ======================= 设置 API =======================


@app.get("/api/settings")
async def api_get_settings():
    """读取全部设置"""
    from mybiout.pages.ohmyconfig.ohmyconfig import get_settings

    return get_settings()


@app.post("/api/setting")
async def api_save_setting(request: Request):
    """保存单项设置 (带校验)"""
    body = await request.json()
    section: str = body.get("section", "")
    key: str = body.get("key", "")
    value: str = body.get("value", "")

    from mybiout.pages.ohmyconfig.ohmyconfig import validate_and_save

    result = validate_and_save(section, key, value)
    if result["ok"]:
        return result
    return JSONResponse(status_code=400, content=result)


@app.post("/api/browse-folder")
def api_browse_folder():
    """
    弹出系统文件夹选择对话框.
    同步端点 —— tkinter 需要在普通线程运行.
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import browse_folder

    path = browse_folder()
    if path:
        return {"ok": True, "path": path}
    return {"ok": False}


@app.get("/api/desktop-path")
async def api_desktop_path():
    """获取桌面 MyBiOut! 路径"""
    from mybiout.pages.ohmyconfig.ohmyconfig import get_desktop_path

    return {"path": get_desktop_path()}


@app.get("/api/default-bili-pc-cache-path")
async def api_default_bili_pc_cache_path():
    """获取默认哔哩哔哩电脑端缓存路径"""
    from mybiout.pages.ohmyconfig.ohmyconfig import get_default_bili_pc_cache_path

    return {"path": get_default_bili_pc_cache_path()}