r"""
MyBiOut! FastAPI 应用定义与全部路由注册

:file: mybiout/pages/apis.py
:author: WaterRun
:time: 2026-04-06
"""

from pathlib import Path as 路径
from typing import Any as 任意

from fastapi import FastAPI as 快速应用
from fastapi import Request as 请求
from fastapi import Response as 响应
from fastapi.responses import HTMLResponse as 网页响应
from fastapi.responses import JSONResponse as 数据响应
from fastapi.staticfiles import StaticFiles as 静态文件

_页面目录: 路径 = 路径(__file__).resolve().parent
_资源目录: 路径 = _页面目录.parent / "assets"

应用: 快速应用 = 快速应用(title="MyBiOut!", version="0.1.0")
应用.mount("/assets", 静态文件(directory=str(_资源目录)), name="assets")
app = 应用


class _无效JSON请求体(ValueError):
    pass


@应用.exception_handler(_无效JSON请求体)
async def _无效JSON处理器(_request: 请求, _exc: _无效JSON请求体) -> 数据响应:
    return 数据响应(status_code=400, content={"ok": False, "error": "请求体不是合法 JSON"})


def _读取网页(relative_path: str) -> 网页响应:
    r"""
    读取 HTML 文件并返回 HTMLResponse
    :param: relative_path: 相对于 pages 目录的路径
    :return: HTMLResponse: 页面内容
    """
    html_path: 路径 = _页面目录 / relative_path
    html_text: str = html_path.read_text(encoding="utf-8")
    return 网页响应(html_text)


async def _读取数据字典(request: 请求) -> dict[str, 任意]:
    r"""
    将请求体读取为 JSON 对象字典
    :param: request: FastAPI 请求对象
    :return: dict[str, Any]: JSON 字典, 若非对象则返回空字典
    """
    try:
        payload: 任意 = await request.json()
    except Exception as e:
        raise _无效JSON请求体 from e
    return payload if isinstance(payload, dict) else {}


def _转字符串(value: 任意) -> str:
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


def _转字符串列表(value: 任意) -> list[str]:
    r"""
    将任意值安全转换为字符串列表
    :param: value: 任意输入值
    :return: list[str]: 字符串列表
    """
    if not isinstance(value, list):
        return []
    return [_转字符串(item) for item in value]


@应用.get("/", response_class=网页响应)
async def 首页() -> 网页响应:
    r"""
    首页路由
    :return: HTMLResponse: 首页 HTML
    """
    return _读取网页("index.html")


@应用.get("/ohmyconfig", response_class=网页响应)
async def 设置页面() -> 网页响应:
    r"""
    设置页路由
    :return: HTMLResponse: 设置页 HTML
    """
    return _读取网页("ohmyconfig/ohmyconfig.html")


@应用.get("/localout", response_class=网页响应)
async def 本地导出页面() -> 网页响应:
    r"""
    本地缓存导出页路由
    :return: HTMLResponse: LocalOut 页 HTML
    """
    return _读取网页("localout/localout.html")


@应用.get("/bbdown", response_class=网页响应)
async def 下载页面() -> 网页响应:
    r"""
    BBDown 下载页路由
    :return: HTMLResponse: BBDown 页 HTML
    """
    return _读取网页("bbdown/bbdown.html")


@应用.get("/mdout", response_class=网页响应)
async def 文档导出页面() -> 网页响应:
    r"""
    Markdown 导出页路由
    :return: HTMLResponse: MdOut 页 HTML
    """
    return _读取网页("mdout/mdout.html")


@应用.get("/man", response_class=网页响应)
async def 手册页面() -> 网页响应:
    r"""
    ManualScript 手册页路由
    :return: HTMLResponse: Man 页 HTML
    """
    return _读取网页("man/man.html")


@应用.get("/api/settings")
async def 取设置接口() -> dict[str, dict[str, str]]:
    r"""
    获取全部设置项
    :return: dict[str, dict[str, str]]: 分区组织的设置
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import get_settings

    return get_settings()


@应用.post("/api/setting")
async def 保存设置接口(request: 请求) -> 响应:
    r"""
    保存单项设置
    :param: request: 请求对象, body 包含 section/key/value
    :return: Response: JSON 响应, 成功 200, 失败 400
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    section: str = _转字符串(body.get("section", ""))
    key: str = _转字符串(body.get("key", ""))
    value: str = _转字符串(body.get("value", ""))

    from mybiout.pages.ohmyconfig.ohmyconfig import validate_and_save

    result: dict[str, bool | str] = validate_and_save(section, key, value)
    status_code: int = 200 if bool(result.get("ok")) else 400
    return 数据响应(status_code=status_code, content=result)


@应用.post("/api/browse-folder")
def 浏览文件夹接口() -> dict[str, bool | str]:
    r"""
    弹出系统文件夹选择对话框
    :return: dict[str, bool | str]: 选择结果
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import browse_folder

    path: str | None = browse_folder()
    return {"ok": True, "path": path} if path else {"ok": False}


@应用.get("/api/desktop-path")
async def 桌面路径接口() -> dict[str, str]:
    r"""
    获取桌面下的默认导出路径
    :return: dict[str, str]: 路径信息
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import get_desktop_path

    return {"path": get_desktop_path()}


@应用.get("/api/default-bili-pc-cache-path")
async def 默认缓存路径接口() -> dict[str, str]:
    r"""
    获取默认哔哩哔哩桌面端缓存路径
    :return: dict[str, str]: 路径信息
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import get_default_bili_pc_cache_path

    return {"path": get_default_bili_pc_cache_path()}


@应用.get("/api/localout/state")
async def 本地导出状态() -> dict[str, 任意]:
    r"""
    获取 LocalOut 当前状态快照
    :return: dict[str, Any]: 状态数据
    """
    from mybiout.pages.localout.localout import get_state

    return get_state()


@应用.get("/api/localout/env-status")
async def 本地导出环境状态() -> dict[str, 任意]:
    r"""
    获取环境状态信息（ADB、biliffm4s 等）
    :return: dict[str, Any]: 环境状态
    """
    from mybiout.pages.localout.localout import get_env_status

    return get_env_status()


@应用.get("/api/localout/available-sources")
async def 本地导出可用来源() -> dict[str, 任意]:
    r"""
    获取可用的扫描源列表和环境警告
    :return: dict[str, Any]: 包含 sources 和 warnings
    """
    from mybiout.pages.localout.localout import get_available_sources

    return get_available_sources()


@应用.post("/api/localout/browse-local")
def 本地导出浏览本地() -> dict[str, bool | str]:
    r"""
    弹出文件夹对话框选择本地缓存目录
    :return: dict[str, bool | str]: 选择结果
    """
    from mybiout.pages.localout.localout import browse_local

    path: str | None = browse_local()
    return {"ok": True, "path": path} if path else {"ok": False}


@应用.post("/api/localout/add-source")
async def 本地导出添加来源(request: 请求) -> dict[str, 任意]:
    r"""
    添加扫描源
    :param: request: 请求对象, body 包含 source_type/path/label/serial/package
    :return: dict[str, Any]: 添加结果
    """
    body: dict[str, 任意] = await _读取数据字典(request)

    from mybiout.pages.localout.localout import add_source

    return add_source(
        source_type=_转字符串(body.get("source_type", "")),
        path=_转字符串(body.get("path", "")),
        label=_转字符串(body.get("label", "")),
        serial=_转字符串(body.get("serial", "")),
        package=_转字符串(body.get("package", "")),
    )


@应用.post("/api/localout/pause-scan")
async def 本地导出暂停扫描() -> dict[str, bool]:
    r"""
    暂停当前扫描
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import pause_scan

    pause_scan()
    return {"ok": True}


@应用.post("/api/localout/resume-scan")
async def 本地导出继续扫描() -> dict[str, bool]:
    r"""
    恢复暂停的扫描
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import resume_scan

    resume_scan()
    return {"ok": True}


@应用.post("/api/localout/cancel-scan")
async def 本地导出取消扫描() -> dict[str, bool]:
    r"""
    取消当前扫描
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import cancel_scan

    cancel_scan()
    return {"ok": True}


@应用.post("/api/localout/add-to-tasks")
async def 本地导出加入任务(request: 请求) -> dict[str, 任意]:
    r"""
    将源卡片添加到任务栏
    :param: request: 请求对象, body 包含 card_ids
    :return: dict[str, Any]: 添加结果
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    card_ids: list[str] = _转字符串列表(body.get("card_ids", []))

    from mybiout.pages.localout.localout import add_to_tasks

    return add_to_tasks(card_ids)


@应用.post("/api/localout/remove-source")
async def 本地导出移除来源(request: 请求) -> dict[str, bool]:
    r"""
    移除指定源卡片
    :param: request: 请求对象, body 包含 card_ids
    :return: dict[str, bool]: 操作结果
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    card_ids: list[str] = _转字符串列表(body.get("card_ids", []))

    from mybiout.pages.localout.localout import remove_source_cards

    remove_source_cards(card_ids)
    return {"ok": True}


@应用.post("/api/localout/remove-tasks")
async def 本地导出移除任务(request: 请求) -> dict[str, bool]:
    r"""
    移除指定任务卡片
    :param: request: 请求对象, body 包含 card_ids
    :return: dict[str, bool]: 操作结果
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    card_ids: list[str] = _转字符串列表(body.get("card_ids", []))

    from mybiout.pages.localout.localout import remove_task_cards

    remove_task_cards(card_ids)
    return {"ok": True}


@应用.post("/api/localout/clear-source")
async def 本地导出清空来源() -> dict[str, bool]:
    r"""
    清空源栏
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import clear_source

    clear_source()
    return {"ok": True}


@应用.post("/api/localout/clear-tasks")
async def 本地导出清空任务() -> dict[str, bool]:
    r"""
    清空任务栏
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import clear_tasks

    clear_tasks()
    return {"ok": True}


@应用.post("/api/localout/clear-completed")
async def 本地导出清空完成() -> dict[str, bool]:
    r"""
    清空完成栏
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import clear_completed

    clear_completed()
    return {"ok": True}


@应用.post("/api/localout/start-export")
async def 本地导出开始导出(request: 请求) -> dict[str, 任意]:
    r"""
    开始导出任务
    :param: request: 请求对象, body 包含 card_ids
    :return: dict[str, Any]: 导出结果
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    card_ids: list[str] = _转字符串列表(body.get("card_ids", []))

    from mybiout.pages.localout.localout import start_export

    return start_export(card_ids)


@应用.get("/api/localout/cover/{card_id}")
async def 本地导出封面(card_id: str) -> 响应:
    r"""
    返回指定卡片的封面图片
    """
    from mybiout.pages.localout.localout import get_cover_bytes

    if result := get_cover_bytes(card_id):
        data, ct = result
        return 响应(content=data, media_type=ct, headers={"Cache-Control": "max-age=300"})
    return 响应(status_code=404)


@应用.post("/api/localout/cancel-export")
async def 本地导出取消导出() -> dict[str, bool]:
    r"""
    取消正在进行的导出
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import cancel_export

    cancel_export()
    return {"ok": True}


@应用.get("/api/bbdown/state")
async def 下载状态() -> dict[str, 任意]:
    r"""
    获取 BBDown 当前状态快照
    :return: dict[str, Any]: 状态数据
    """
    from mybiout.pages.bbdown.bbdown import get_state

    return get_state()


@应用.get("/api/bbdown/env-check")
async def 下载环境检查() -> dict[str, 任意]:
    r"""
    检查 BBDown 运行环境
    :return: dict[str, Any]: 环境检测结果
    """
    from mybiout.pages.bbdown.bbdown import env_check

    return env_check()


@应用.post("/api/bbdown/add")
async def 下载添加任务(request: 请求) -> 响应:
    r"""
    添加 BBDown 下载任务
    :param: request: 请求对象, body 包含 url/options
    :return: Response: JSON 响应, 成功 200, 失败 400
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    url: str = _转字符串(body.get("url", ""))
    options: 任意 = body.get("options")

    from mybiout.pages.bbdown.bbdown import add_task

    result: dict[str, 任意] = add_task(url, options)
    status_code: int = 200 if bool(result.get("ok")) else 400
    return 数据响应(status_code=status_code, content=result)


@应用.post("/api/bbdown/cancel")
async def 下载取消当前() -> dict[str, bool]:
    r"""
    取消当前 BBDown 下载
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.bbdown.bbdown import cancel_current

    cancel_current()
    return {"ok": True}


@应用.post("/api/bbdown/retry")
async def 下载重试任务(request: 请求) -> dict[str, 任意]:
    r"""
    重试失败的 BBDown 任务
    :param: request: 请求对象, body 包含 task_id
    :return: dict[str, Any]: 操作结果
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    task_id: str = _转字符串(body.get("task_id", ""))

    from mybiout.pages.bbdown.bbdown import retry_task

    return retry_task(task_id)


@应用.post("/api/bbdown/remove")
async def 下载移除任务(request: 请求) -> dict[str, bool]:
    r"""
    移除 BBDown 任务
    :param: request: 请求对象, body 包含 task_id
    :return: dict[str, bool]: 操作结果
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    task_id: str = _转字符串(body.get("task_id", ""))

    from mybiout.pages.bbdown.bbdown import remove_task

    remove_task(task_id)
    return {"ok": True}


@应用.post("/api/bbdown/clear-completed")
async def 下载清空完成() -> dict[str, bool]:
    r"""
    清空 BBDown 已完成列表
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.bbdown.bbdown import clear_completed

    clear_completed()
    return {"ok": True}


@应用.post("/api/bbdown/clear-failed")
async def 下载清空失败() -> dict[str, bool]:
    r"""
    清空 BBDown 失败任务
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.bbdown.bbdown import clear_failed

    clear_failed()
    return {"ok": True}


@应用.post("/api/bbdown/clear-queue")
async def 下载清空队列() -> dict[str, bool]:
    r"""
    清空 BBDown 排队任务
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.bbdown.bbdown import clear_queue

    clear_queue()
    return {"ok": True}


@应用.get("/api/mdout/state")
async def 文档导出状态() -> dict[str, 任意]:
    r"""
    获取 MdOut 当前状态快照
    :return: dict[str, Any]: 状态数据
    """
    from mybiout.pages.mdout.mdout import get_state

    return get_state()


@应用.post("/api/mdout/parse")
async def 文档导出解析(request: 请求) -> dict[str, 任意]:
    r"""
    解析输入文本识别类型
    :param: request: 请求对象, body 包含 text
    :return: dict[str, Any]: 解析结果
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    text: str = _转字符串(body.get("text", ""))

    from mybiout.pages.mdout.mdout import do_parse

    return do_parse(text)


@应用.post("/api/mdout/add")
async def 文档导出添加(request: 请求) -> 响应:
    r"""
    添加 MdOut 获取任务
    :param: request: 请求对象, body 包含 text
    :return: Response: JSON 响应, 成功 200, 失败 400
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    text: str = _转字符串(body.get("text", ""))

    from mybiout.pages.mdout.mdout import add_and_fetch

    result: dict[str, 任意] = add_and_fetch(text)
    status_code: int = 200 if bool(result.get("ok")) else 400
    return 数据响应(status_code=status_code, content=result)


@应用.post("/api/mdout/select")
async def 文档导出选择(request: 请求) -> dict[str, bool]:
    r"""
    选中 MdOut 卡片以预览
    :param: request: 请求对象, body 包含 card_id
    :return: dict[str, bool]: 操作结果
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    card_id: str = _转字符串(body.get("card_id", ""))

    from mybiout.pages.mdout.mdout import select_card

    select_card(card_id)
    return {"ok": True}


@应用.post("/api/mdout/export")
async def 文档导出执行(request: 请求) -> dict[str, 任意]:
    r"""
    导出指定 MdOut 卡片
    :param: request: 请求对象, body 包含 card_ids
    :return: dict[str, Any]: 导出结果
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    card_ids: list[str] = _转字符串列表(body.get("card_ids", []))

    from mybiout.pages.mdout.mdout import export_cards

    return export_cards(card_ids)


@应用.post("/api/mdout/export-all")
async def 文档导出全部() -> dict[str, 任意]:
    r"""
    导出全部就绪的 MdOut 卡片
    :return: dict[str, Any]: 导出结果
    """
    from mybiout.pages.mdout.mdout import export_all_ready

    return export_all_ready()


@应用.post("/api/mdout/remove")
async def 文档导出移除(request: 请求) -> dict[str, bool]:
    r"""
    移除指定 MdOut 卡片
    :param: request: 请求对象, body 包含 card_ids
    :return: dict[str, bool]: 操作结果
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    card_ids: list[str] = _转字符串列表(body.get("card_ids", []))

    from mybiout.pages.mdout.mdout import remove_cards

    remove_cards(card_ids)
    return {"ok": True}


@应用.post("/api/mdout/clear")
async def 文档导出清空() -> dict[str, bool]:
    r"""
    清空全部 MdOut 卡片
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.mdout.mdout import clear_cards

    clear_cards()
    return {"ok": True}


@应用.post("/api/mdout/clear-completed")
async def 文档导出清空完成() -> dict[str, bool]:
    r"""
    清空 MdOut 已完成列表
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.mdout.mdout import clear_completed

    clear_completed()
    return {"ok": True}


@应用.post("/api/man/chat")
async def 手册对话(request: 请求) -> dict[str, 任意]:
    r"""
    Man 页面 AI 对话接口
    :param: request: 请求对象, body 包含 prompt 和可选 force_bs
    :return: dict[str, Any]: 对话结果, 包含 reply/source/note
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    prompt: str = _转字符串(body.get("prompt", ""))
    force_bs: bool = bool(body.get("force_bs", False))

    from mybiout.pages.man.man import chat

    return chat(prompt, force_bs=force_bs)


@应用.post("/api/open-explorer")
async def 打开资源管理器接口(request: 请求) -> dict[str, bool | str]:
    r"""
    在资源管理器中定位文件
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    path: str = _转字符串(body.get("path", ""))

    from mybiout.pages.bbdown.bbdown import open_in_explorer

    return open_in_explorer(path)


@应用.post("/api/auto-sessdata")
async def 自动会话数据接口(request: 请求) -> dict[str, 任意]:
    r"""
    通过扫码登录获取 SESSDATA:
    action: "launch_login"
    """
    body: dict[str, 任意] = await _读取数据字典(request)
    action: str = _转字符串(body.get("action", "launch_login"))
    user_agent = request.headers.get("user-agent", "")

    from mybiout.pages.ohmyconfig.ohmyconfig import _auto_get_sessdata_via_login

    if action == "launch_login":
        result = _auto_get_sessdata_via_login(user_agent, timeout_sec=180)
        if result:
            return {"status": "success", "sessdata": result}
        return {"status": "failed", "error": "扫码登录超时或窗口被关闭"}

    return {"status": "failed", "error": "已移除浏览器 Cookie 自动提取能力，请使用扫码登录"}


@应用.post("/api/reset-all-settings")
async def 重置全部设置接口() -> dict[str, bool]:
    r"""
    恢复全部默认设置
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import reset_all

    return reset_all()


@应用.post("/api/mdout/open-folder")
async def 文档导出打开目录() -> dict[str, bool | str]:
    r"""
    打开 MdOut 导出目录
    """
    from mybiout.pages.bbdown.bbdown import open_in_explorer
    from mybiout.pages.mdout.mdout import get_export_folder_path

    return open_in_explorer(get_export_folder_path())


@应用.post("/api/man/chat-stream")
async def 手册流式对话(request: 请求):
    r"""
    Man 页面 AI 流式对话接口 (SSE)
    """
    from fastapi.responses import StreamingResponse

    body: dict[str, 任意] = await _读取数据字典(request)
    prompt: str = _转字符串(body.get("prompt", ""))

    from mybiout.pages.man.man import chat_stream_sse

    return StreamingResponse(
        chat_stream_sse(prompt),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_PAGES_DIR = _页面目录
_ASSETS_DIR = _资源目录
_InvalidJsonBody = _无效JSON请求体
_invalid_json_handler = _无效JSON处理器
_read_html = _读取网页
_read_json_dict = _读取数据字典
_as_str = _转字符串
_as_str_list = _转字符串列表

index = 首页
ohmyconfig_page = 设置页面
localout_page = 本地导出页面
bbdown_page = 下载页面
mdout_page = 文档导出页面
man_page = 手册页面
api_get_settings = 取设置接口
api_save_setting = 保存设置接口
api_browse_folder = 浏览文件夹接口
api_desktop_path = 桌面路径接口
api_default_bili_pc_cache_path = 默认缓存路径接口
localout_state = 本地导出状态
localout_env_status = 本地导出环境状态
localout_available_sources = 本地导出可用来源
localout_browse_local = 本地导出浏览本地
localout_add_source = 本地导出添加来源
localout_pause_scan = 本地导出暂停扫描
localout_resume_scan = 本地导出继续扫描
localout_cancel_scan = 本地导出取消扫描
localout_add_to_tasks = 本地导出加入任务
localout_remove_source = 本地导出移除来源
localout_remove_tasks = 本地导出移除任务
localout_clear_source = 本地导出清空来源
localout_clear_tasks = 本地导出清空任务
localout_clear_completed = 本地导出清空完成
localout_start_export = 本地导出开始导出
localout_cover = 本地导出封面
localout_cancel_export = 本地导出取消导出
bbdown_state = 下载状态
bbdown_env_check = 下载环境检查
bbdown_add = 下载添加任务
bbdown_cancel = 下载取消当前
bbdown_retry = 下载重试任务
bbdown_remove = 下载移除任务
bbdown_clear_completed = 下载清空完成
bbdown_clear_failed = 下载清空失败
bbdown_clear_queue = 下载清空队列
mdout_state = 文档导出状态
mdout_parse = 文档导出解析
mdout_add = 文档导出添加
mdout_select = 文档导出选择
mdout_export = 文档导出执行
mdout_export_all = 文档导出全部
mdout_remove = 文档导出移除
mdout_clear = 文档导出清空
mdout_clear_completed = 文档导出清空完成
man_chat = 手册对话
api_open_explorer = 打开资源管理器接口
api_auto_sessdata = 自动会话数据接口
api_reset_all_settings = 重置全部设置接口
mdout_open_folder = 文档导出打开目录
man_chat_stream = 手册流式对话
