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
    return HTMLResponse(
        (_PAGES_DIR / "index.html").read_text(encoding="utf-8")
    )


@app.get("/ohmyconfig", response_class=HTMLResponse)
async def ohmyconfig_page() -> HTMLResponse:
    return HTMLResponse(
        (_PAGES_DIR / "ohmyconfig" / "ohmyconfig.html").read_text(encoding="utf-8")
    )


@app.get("/localout", response_class=HTMLResponse)
async def localout_page() -> HTMLResponse:
    return HTMLResponse(
        (_PAGES_DIR / "localout" / "localout.html").read_text(encoding="utf-8")
    )


# ======================= 设置 API =======================


@app.get("/api/settings")
async def api_get_settings():
    from mybiout.pages.ohmyconfig.ohmyconfig import get_settings
    return get_settings()


@app.post("/api/setting")
async def api_save_setting(request: Request):
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
    from mybiout.pages.ohmyconfig.ohmyconfig import browse_folder
    path = browse_folder()
    if path:
        return {"ok": True, "path": path}
    return {"ok": False}


@app.get("/api/desktop-path")
async def api_desktop_path():
    from mybiout.pages.ohmyconfig.ohmyconfig import get_desktop_path
    return {"path": get_desktop_path()}


@app.get("/api/default-bili-pc-cache-path")
async def api_default_bili_pc_cache_path():
    from mybiout.pages.ohmyconfig.ohmyconfig import get_default_bili_pc_cache_path
    return {"path": get_default_bili_pc_cache_path()}


# ======================= LocalOut API =======================


@app.get("/api/localout/state")
async def localout_state():
    from mybiout.pages.localout.localout import get_state
    return get_state()


@app.get("/api/localout/available-sources")
async def localout_available_sources():
    from mybiout.pages.localout.localout import get_available_sources
    return get_available_sources()


@app.post("/api/localout/browse-local")
def localout_browse_local():
    from mybiout.pages.localout.localout import browse_local
    path = browse_local()
    if path:
        return {"ok": True, "path": path}
    return {"ok": False}


@app.post("/api/localout/add-source")
async def localout_add_source(request: Request):
    body = await request.json()
    from mybiout.pages.localout.localout import add_source
    return add_source(
        source_type=body.get("source_type", ""),
        path=body.get("path", ""),
        label=body.get("label", ""),
        serial=body.get("serial", ""),
        package=body.get("package", ""),
    )


@app.post("/api/localout/pause-scan")
async def localout_pause_scan():
    from mybiout.pages.localout.localout import pause_scan
    pause_scan()
    return {"ok": True}


@app.post("/api/localout/resume-scan")
async def localout_resume_scan():
    from mybiout.pages.localout.localout import resume_scan
    resume_scan()
    return {"ok": True}


@app.post("/api/localout/cancel-scan")
async def localout_cancel_scan():
    from mybiout.pages.localout.localout import cancel_scan
    cancel_scan()
    return {"ok": True}


@app.post("/api/localout/add-to-tasks")
async def localout_add_to_tasks(request: Request):
    body = await request.json()
    from mybiout.pages.localout.localout import add_to_tasks
    return add_to_tasks(body.get("card_ids", []))


@app.post("/api/localout/remove-source")
async def localout_remove_source(request: Request):
    body = await request.json()
    from mybiout.pages.localout.localout import remove_source_cards
    remove_source_cards(body.get("card_ids", []))
    return {"ok": True}


@app.post("/api/localout/remove-tasks")
async def localout_remove_tasks(request: Request):
    body = await request.json()
    from mybiout.pages.localout.localout import remove_task_cards
    remove_task_cards(body.get("card_ids", []))
    return {"ok": True}


@app.post("/api/localout/clear-source")
async def localout_clear_source():
    from mybiout.pages.localout.localout import clear_source
    clear_source()
    return {"ok": True}


@app.post("/api/localout/clear-tasks")
async def localout_clear_tasks():
    from mybiout.pages.localout.localout import clear_tasks
    clear_tasks()
    return {"ok": True}


@app.post("/api/localout/clear-completed")
async def localout_clear_completed():
    from mybiout.pages.localout.localout import clear_completed
    clear_completed()
    return {"ok": True}


@app.post("/api/localout/start-export")
async def localout_start_export(request: Request):
    body = await request.json()
    from mybiout.pages.localout.localout import start_export
    return start_export(body.get("card_ids", []))


@app.post("/api/localout/cancel-export")
async def localout_cancel_export():
    from mybiout.pages.localout.localout import cancel_export
    cancel_export()
    return {"ok": True}