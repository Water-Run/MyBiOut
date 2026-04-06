r"""
MyBiOut! FastAPI 应用定义与全部路由注册

:file: mybiout/pages/apis.py
:author: WaterRun
:time: 2026-03-31
"""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

_PAGES_DIR: Path = Path(__file__).resolve().parent
_ASSETS_DIR: Path = _PAGES_DIR.parent / "assets"

app: FastAPI = FastAPI(title="MyBiOut!", version="0.1.0")
app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")


def _read_html(relative_path: str) -> HTMLResponse:
    r"""
    读取 HTML 文件并返回 HTMLResponse
    :param: relative_path: 相对于 pages 目录的路径
    :return: HTMLResponse: 页面内容
    """
    html_path: Path = _PAGES_DIR / relative_path
    html_text: str = html_path.read_text(encoding="utf-8")
    return HTMLResponse(html_text)


async def _read_json_dict(request: Request) -> dict[str, Any]:
    r"""
    将请求体读取为 JSON 对象字典
    :param: request: FastAPI 请求对象
    :return: dict[str, Any]: JSON 字典, 若非对象则返回空字典
    """
    payload: Any = await request.json()
    return payload if isinstance(payload, dict) else {}


def _as_str(value: Any) -> str:
    r"""
    将任意值安全转换为字符串
    :param: value: 任意输入值
    :return: str: 转换后的字符串
    """
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _as_str_list(value: Any) -> list[str]:
    r"""
    将任意值安全转换为字符串列表
    :param: value: 任意输入值
    :return: list[str]: 字符串列表
    """
    if not isinstance(value, list):
        return []
    return [_as_str(item) for item in value]


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    r"""
    首页路由
    :return: HTMLResponse: 首页 HTML
    """
    return _read_html("index.html")


@app.get("/ohmyconfig", response_class=HTMLResponse)
async def ohmyconfig_page() -> HTMLResponse:
    r"""
    设置页路由
    :return: HTMLResponse: 设置页 HTML
    """
    return _read_html("ohmyconfig/ohmyconfig.html")


@app.get("/localout", response_class=HTMLResponse)
async def localout_page() -> HTMLResponse:
    r"""
    本地缓存导出页路由
    :return: HTMLResponse: LocalOut 页 HTML
    """
    return _read_html("localout/localout.html")


@app.get("/bbdown", response_class=HTMLResponse)
async def bbdown_page() -> HTMLResponse:
    r"""
    BBDown 下载页路由
    :return: HTMLResponse: BBDown 页 HTML
    """
    return _read_html("bbdown/bbdown.html")


@app.get("/mdout", response_class=HTMLResponse)
async def mdout_page() -> HTMLResponse:
    r"""
    Markdown 导出页路由
    :return: HTMLResponse: MdOut 页 HTML
    """
    return _read_html("mdout/mdout.html")


@app.get("/man", response_class=HTMLResponse)
async def man_page() -> HTMLResponse:
    r"""
    ManualScript 手册页路由
    :return: HTMLResponse: Man 页 HTML
    """
    return _read_html("man/man.html")


@app.get("/api/settings")
async def api_get_settings() -> dict[str, dict[str, str]]:
    r"""
    获取全部设置项
    :return: dict[str, dict[str, str]]: 分区组织的设置
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import get_settings

    return get_settings()


@app.post("/api/setting")
async def api_save_setting(request: Request) -> Response:
    r"""
    保存单项设置
    :param: request: 请求对象, body 包含 section/key/value
    :return: Response: JSON 响应, 成功 200, 失败 400
    """
    body: dict[str, Any] = await _read_json_dict(request)
    section: str = _as_str(body.get("section", ""))
    key: str = _as_str(body.get("key", ""))
    value: str = _as_str(body.get("value", ""))

    from mybiout.pages.ohmyconfig.ohmyconfig import validate_and_save

    result: dict[str, bool | str] = validate_and_save(section, key, value)
    status_code: int = 200 if bool(result.get("ok")) else 400
    return JSONResponse(status_code=status_code, content=result)


@app.post("/api/browse-folder")
def api_browse_folder() -> dict[str, bool | str]:
    r"""
    弹出系统文件夹选择对话框
    :return: dict[str, bool | str]: 选择结果
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import browse_folder

    path: str | None = browse_folder()
    return {"ok": True, "path": path} if path else {"ok": False}


@app.get("/api/desktop-path")
async def api_desktop_path() -> dict[str, str]:
    r"""
    获取桌面下的默认导出路径
    :return: dict[str, str]: 路径信息
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import get_desktop_path

    return {"path": get_desktop_path()}


@app.get("/api/default-bili-pc-cache-path")
async def api_default_bili_pc_cache_path() -> dict[str, str]:
    r"""
    获取默认哔哩哔哩桌面端缓存路径
    :return: dict[str, str]: 路径信息
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import get_default_bili_pc_cache_path

    return {"path": get_default_bili_pc_cache_path()}


@app.get("/api/localout/state")
async def localout_state() -> dict[str, Any]:
    r"""
    获取 LocalOut 当前状态快照
    :return: dict[str, Any]: 状态数据
    """
    from mybiout.pages.localout.localout import get_state

    return get_state()


@app.get("/api/localout/available-sources")
async def localout_available_sources() -> list[dict[str, Any]]:
    r"""
    获取可用的扫描源列表
    :return: list[dict[str, Any]]: 可用源
    """
    from mybiout.pages.localout.localout import get_available_sources

    return get_available_sources()


@app.post("/api/localout/browse-local")
def localout_browse_local() -> dict[str, bool | str]:
    r"""
    弹出文件夹对话框选择本地缓存目录
    :return: dict[str, bool | str]: 选择结果
    """
    from mybiout.pages.localout.localout import browse_local

    path: str | None = browse_local()
    return {"ok": True, "path": path} if path else {"ok": False}


@app.post("/api/localout/add-source")
async def localout_add_source(request: Request) -> dict[str, Any]:
    r"""
    添加扫描源
    :param: request: 请求对象, body 包含 source_type/path/label/serial/package
    :return: dict[str, Any]: 添加结果
    """
    body: dict[str, Any] = await _read_json_dict(request)

    from mybiout.pages.localout.localout import add_source

    return add_source(
        source_type=_as_str(body.get("source_type", "")),
        path=_as_str(body.get("path", "")),
        label=_as_str(body.get("label", "")),
        serial=_as_str(body.get("serial", "")),
        package=_as_str(body.get("package", "")),
    )


@app.post("/api/localout/pause-scan")
async def localout_pause_scan() -> dict[str, bool]:
    r"""
    暂停当前扫描
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import pause_scan

    pause_scan()
    return {"ok": True}


@app.post("/api/localout/resume-scan")
async def localout_resume_scan() -> dict[str, bool]:
    r"""
    恢复暂停的扫描
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import resume_scan

    resume_scan()
    return {"ok": True}


@app.post("/api/localout/cancel-scan")
async def localout_cancel_scan() -> dict[str, bool]:
    r"""
    取消当前扫描
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import cancel_scan

    cancel_scan()
    return {"ok": True}


@app.post("/api/localout/add-to-tasks")
async def localout_add_to_tasks(request: Request) -> dict[str, Any]:
    r"""
    将源卡片添加到任务栏
    :param: request: 请求对象, body 包含 card_ids
    :return: dict[str, Any]: 添加结果
    """
    body: dict[str, Any] = await _read_json_dict(request)
    card_ids: list[str] = _as_str_list(body.get("card_ids", []))

    from mybiout.pages.localout.localout import add_to_tasks

    return add_to_tasks(card_ids)


@app.post("/api/localout/remove-source")
async def localout_remove_source(request: Request) -> dict[str, bool]:
    r"""
    移除指定源卡片
    :param: request: 请求对象, body 包含 card_ids
    :return: dict[str, bool]: 操作结果
    """
    body: dict[str, Any] = await _read_json_dict(request)
    card_ids: list[str] = _as_str_list(body.get("card_ids", []))

    from mybiout.pages.localout.localout import remove_source_cards

    remove_source_cards(card_ids)
    return {"ok": True}


@app.post("/api/localout/remove-tasks")
async def localout_remove_tasks(request: Request) -> dict[str, bool]:
    r"""
    移除指定任务卡片
    :param: request: 请求对象, body 包含 card_ids
    :return: dict[str, bool]: 操作结果
    """
    body: dict[str, Any] = await _read_json_dict(request)
    card_ids: list[str] = _as_str_list(body.get("card_ids", []))

    from mybiout.pages.localout.localout import remove_task_cards

    remove_task_cards(card_ids)
    return {"ok": True}


@app.post("/api/localout/clear-source")
async def localout_clear_source() -> dict[str, bool]:
    r"""
    清空源栏
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import clear_source

    clear_source()
    return {"ok": True}


@app.post("/api/localout/clear-tasks")
async def localout_clear_tasks() -> dict[str, bool]:
    r"""
    清空任务栏
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import clear_tasks

    clear_tasks()
    return {"ok": True}


@app.post("/api/localout/clear-completed")
async def localout_clear_completed() -> dict[str, bool]:
    r"""
    清空完成栏
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import clear_completed

    clear_completed()
    return {"ok": True}


@app.post("/api/localout/start-export")
async def localout_start_export(request: Request) -> dict[str, Any]:
    r"""
    开始导出任务
    :param: request: 请求对象, body 包含 card_ids
    :return: dict[str, Any]: 导出结果
    """
    body: dict[str, Any] = await _read_json_dict(request)
    card_ids: list[str] = _as_str_list(body.get("card_ids", []))

    from mybiout.pages.localout.localout import start_export

    return start_export(card_ids)


@app.post("/api/localout/cancel-export")
async def localout_cancel_export() -> dict[str, bool]:
    r"""
    取消正在进行的导出
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import cancel_export

    cancel_export()
    return {"ok": True}


@app.get("/api/bbdown/state")
async def bbdown_state() -> dict[str, Any]:
    r"""
    获取 BBDown 当前状态快照
    :return: dict[str, Any]: 状态数据
    """
    from mybiout.pages.bbdown.bbdown import get_state

    return get_state()


@app.get("/api/bbdown/env-check")
async def bbdown_env_check() -> dict[str, Any]:
    r"""
    检查 BBDown 运行环境
    :return: dict[str, Any]: 环境检测结果
    """
    from mybiout.pages.bbdown.bbdown import env_check

    return env_check()


@app.post("/api/bbdown/add")
async def bbdown_add(request: Request) -> Response:
    r"""
    添加 BBDown 下载任务
    :param: request: 请求对象, body 包含 url/options
    :return: Response: JSON 响应, 成功 200, 失败 400
    """
    body: dict[str, Any] = await _read_json_dict(request)
    url: str = _as_str(body.get("url", ""))
    options: Any = body.get("options")

    from mybiout.pages.bbdown.bbdown import add_task

    result: dict[str, Any] = add_task(url, options)
    status_code: int = 200 if bool(result.get("ok")) else 400
    return JSONResponse(status_code=status_code, content=result)


@app.post("/api/bbdown/cancel")
async def bbdown_cancel() -> dict[str, bool]:
    r"""
    取消当前 BBDown 下载
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.bbdown.bbdown import cancel_current

    cancel_current()
    return {"ok": True}


@app.post("/api/bbdown/retry")
async def bbdown_retry(request: Request) -> dict[str, Any]:
    r"""
    重试失败的 BBDown 任务
    :param: request: 请求对象, body 包含 task_id
    :return: dict[str, Any]: 操作结果
    """
    body: dict[str, Any] = await _read_json_dict(request)
    task_id: str = _as_str(body.get("task_id", ""))

    from mybiout.pages.bbdown.bbdown import retry_task

    return retry_task(task_id)


@app.post("/api/bbdown/remove")
async def bbdown_remove(request: Request) -> dict[str, bool]:
    r"""
    移除 BBDown 任务
    :param: request: 请求对象, body 包含 task_id
    :return: dict[str, bool]: 操作结果
    """
    body: dict[str, Any] = await _read_json_dict(request)
    task_id: str = _as_str(body.get("task_id", ""))

    from mybiout.pages.bbdown.bbdown import remove_task

    remove_task(task_id)
    return {"ok": True}


@app.post("/api/bbdown/clear-completed")
async def bbdown_clear_completed() -> dict[str, bool]:
    r"""
    清空 BBDown 已完成列表
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.bbdown.bbdown import clear_completed

    clear_completed()
    return {"ok": True}


@app.post("/api/bbdown/clear-failed")
async def bbdown_clear_failed() -> dict[str, bool]:
    r"""
    清空 BBDown 失败任务
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.bbdown.bbdown import clear_failed

    clear_failed()
    return {"ok": True}


@app.post("/api/bbdown/clear-queue")
async def bbdown_clear_queue() -> dict[str, bool]:
    r"""
    清空 BBDown 排队任务
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.bbdown.bbdown import clear_queue

    clear_queue()
    return {"ok": True}


@app.get("/api/mdout/state")
async def mdout_state() -> dict[str, Any]:
    r"""
    获取 MdOut 当前状态快照
    :return: dict[str, Any]: 状态数据
    """
    from mybiout.pages.mdout.mdout import get_state

    return get_state()


@app.post("/api/mdout/parse")
async def mdout_parse(request: Request) -> dict[str, Any]:
    r"""
    解析输入文本识别类型
    :param: request: 请求对象, body 包含 text
    :return: dict[str, Any]: 解析结果
    """
    body: dict[str, Any] = await _read_json_dict(request)
    text: str = _as_str(body.get("text", ""))

    from mybiout.pages.mdout.mdout import do_parse

    return do_parse(text)


@app.post("/api/mdout/add")
async def mdout_add(request: Request) -> Response:
    r"""
    添加 MdOut 获取任务
    :param: request: 请求对象, body 包含 text
    :return: Response: JSON 响应, 成功 200, 失败 400
    """
    body: dict[str, Any] = await _read_json_dict(request)
    text: str = _as_str(body.get("text", ""))

    from mybiout.pages.mdout.mdout import add_and_fetch

    result: dict[str, Any] = add_and_fetch(text)
    status_code: int = 200 if bool(result.get("ok")) else 400
    return JSONResponse(status_code=status_code, content=result)


@app.post("/api/mdout/select")
async def mdout_select(request: Request) -> dict[str, bool]:
    r"""
    选中 MdOut 卡片以预览
    :param: request: 请求对象, body 包含 card_id
    :return: dict[str, bool]: 操作结果
    """
    body: dict[str, Any] = await _read_json_dict(request)
    card_id: str = _as_str(body.get("card_id", ""))

    from mybiout.pages.mdout.mdout import select_card

    select_card(card_id)
    return {"ok": True}


@app.post("/api/mdout/export")
async def mdout_export(request: Request) -> dict[str, Any]:
    r"""
    导出指定 MdOut 卡片
    :param: request: 请求对象, body 包含 card_ids
    :return: dict[str, Any]: 导出结果
    """
    body: dict[str, Any] = await _read_json_dict(request)
    card_ids: list[str] = _as_str_list(body.get("card_ids", []))

    from mybiout.pages.mdout.mdout import export_cards

    return export_cards(card_ids)


@app.post("/api/mdout/export-all")
async def mdout_export_all() -> dict[str, Any]:
    r"""
    导出全部就绪的 MdOut 卡片
    :return: dict[str, Any]: 导出结果
    """
    from mybiout.pages.mdout.mdout import export_all_ready

    return export_all_ready()


@app.post("/api/mdout/remove")
async def mdout_remove(request: Request) -> dict[str, bool]:
    r"""
    移除指定 MdOut 卡片
    :param: request: 请求对象, body 包含 card_ids
    :return: dict[str, bool]: 操作结果
    """
    body: dict[str, Any] = await _read_json_dict(request)
    card_ids: list[str] = _as_str_list(body.get("card_ids", []))

    from mybiout.pages.mdout.mdout import remove_cards

    remove_cards(card_ids)
    return {"ok": True}


@app.post("/api/mdout/clear")
async def mdout_clear() -> dict[str, bool]:
    r"""
    清空全部 MdOut 卡片
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.mdout.mdout import clear_cards

    clear_cards()
    return {"ok": True}


@app.post("/api/mdout/clear-completed")
async def mdout_clear_completed() -> dict[str, bool]:
    r"""
    清空 MdOut 已完成列表
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.mdout.mdout import clear_completed

    clear_completed()
    return {"ok": True}


@app.post("/api/man/chat")
async def man_chat(request: Request) -> dict[str, Any]:
    r"""
    Man 页面 AI 对话接口
    :param: request: 请求对象, body 包含 prompt 和可选 force_bs
    :return: dict[str, Any]: 对话结果, 包含 reply/source/note
    """
    body: dict[str, Any] = await _read_json_dict(request)
    prompt: str = _as_str(body.get("prompt", ""))
    force_bs: bool = bool(body.get("force_bs", False))

    from mybiout.pages.man.man import chat

    return chat(prompt, force_bs=force_bs)

@app.post("/api/open-explorer")
async def api_open_explorer(request: Request) -> dict[str, bool | str]:
    r"""
    在资源管理器中定位文件
    """
    body: dict[str, Any] = await _read_json_dict(request)
    path: str = _as_str(body.get("path", ""))

    from mybiout.pages.bbdown.bbdown import open_in_explorer
    return open_in_explorer(path)


@app.post("/api/auto-sessdata")
async def api_auto_sessdata() -> dict[str, bool | str]:
    r"""
    尝试从浏览器自动获取 SESSDATA
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import auto_get_sessdata
    result: str | None = auto_get_sessdata()
    if result:
        return {"ok": True, "sessdata": result}
    return {"ok": False, "error": "无法自动获取, 请手动填写"}


@app.post("/api/man/chat-stream")
async def man_chat_stream(request: Request):
    r"""
    Man 页面 AI 流式对话接口 (SSE)
    """
    from fastapi.responses import StreamingResponse

    body: dict[str, Any] = await _read_json_dict(request)
    prompt: str = _as_str(body.get("prompt", ""))

    from mybiout.pages.man.man import chat_stream_sse

    return StreamingResponse(
        chat_stream_sse(prompt),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
    