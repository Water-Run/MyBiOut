r"""
MyBiOut! FastAPI 应用定义与全部路由注册

:file: mybiout/pages/apis.py
:author: WaterRun
:time: 2026-04-06
"""

from pathlib import Path as 路径
from typing import Any as 任意

from fastapi import FastAPI as 快速应用
from fastapi import Path as 路径参数
from fastapi import Request as 请求
from fastapi import Response as 响应
from fastapi.responses import HTMLResponse as 网页响应
from fastapi.responses import JSONResponse as 数据响应
from fastapi.staticfiles import StaticFiles as 静态文件

from mybiout import 取版本号
from mybiout.pages import utils as 工具

_页面目录: 路径 = 工具.取页面目录()
_资源目录: 路径 = 工具.取静态资源目录()

应用: 快速应用 = 快速应用(title="MyBiOut!", version=取版本号())
应用.mount("/assets", 静态文件(directory=str(_资源目录)), name="assets")


class _无效JSON请求体(ValueError):
    pass


@应用.exception_handler(_无效JSON请求体)
async def _无效JSON处理器(_请求: 请求, _异常: _无效JSON请求体) -> 数据响应:
    return 数据响应(status_code=400, content={"ok": False, "error": "请求体不是合法 JSON"})


def _读取网页(相对路径: str) -> 网页响应:
    r"""
    读取 HTML 文件并返回 HTMLResponse
    :param: 相对路径: 相对于 pages 目录的路径
    :return: HTMLResponse: 页面内容
    """
    网页路径: 路径 = _页面目录 / 相对路径
    网页文本: str = 网页路径.read_text(encoding="utf-8")
    return 网页响应(网页文本)


async def _读取数据字典(请求对象: 请求) -> dict[str, 任意]:
    r"""
    将请求体读取为 JSON 对象字典
    :param: 请求对象: FastAPI 请求对象
    :return: dict[str, Any]: JSON 字典, 若非对象则返回空字典
    """
    try:
        载荷: 任意 = await 请求对象.json()
    except Exception as e:
        raise _无效JSON请求体 from e
    return 载荷 if isinstance(载荷, dict) else {}


def _转字符串(值: 任意) -> str:
    r"""
    将任意值安全转换为字符串
    :param: 值: 任意输入值
    :return: str: 转换后的字符串
    """
    if isinstance(值, str):
        return 值
    if 值 is None:
        return ""
    return str(值)


def _转字符串列表(值: 任意) -> list[str]:
    r"""
    将任意值安全转换为字符串列表
    :param: 值: 任意输入值
    :return: list[str]: 字符串列表
    """
    if not isinstance(值, list):
        return []
    return [_转字符串(项) for 项 in 值]


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


@应用.get("/api/version")
async def 取版本接口() -> dict[str, str]:
    r"""
    动态读取 version.txt 中的版本号 (如 二六〇七甲)
    :return: dict[str, str]: {"version": "..."}
    """
    return {"version": 取版本号()}


@应用.get("/api/settings")
async def 取设置接口() -> dict[str, dict[str, str]]:
    r"""
    获取全部设置项
    :return: dict[str, dict[str, str]]: 分区组织的设置
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import 取设置

    return 取设置()


@应用.post("/api/setting")
async def 保存设置接口(请求对象: 请求) -> 响应:
    r"""
    保存单项设置
    :param: 请求对象: 请求对象, body 包含 section/key/value
    :return: Response: JSON 响应, 成功 200, 失败 400
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    分区: str = _转字符串(请求体.get("section", ""))
    键: str = _转字符串(请求体.get("key", ""))
    值: str = _转字符串(请求体.get("value", ""))

    from mybiout.pages.ohmyconfig.ohmyconfig import 校验并保存

    结果: dict[str, bool | str] = 校验并保存(分区, 键, 值)
    状态码: int = 200 if bool(结果.get("ok")) else 400
    return 数据响应(status_code=状态码, content=结果)


@应用.post("/api/browse-folder")
def 浏览文件夹接口() -> dict[str, bool | str]:
    r"""
    弹出系统文件夹选择对话框
    :return: dict[str, bool | str]: 选择结果
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import 浏览文件夹

    目录路径: str | None = 浏览文件夹()
    return {"ok": True, "path": 目录路径} if 目录路径 else {"ok": False}


@应用.get("/api/desktop-path")
async def 桌面路径接口() -> dict[str, str]:
    r"""
    获取桌面下的默认导出路径
    :return: dict[str, str]: 路径信息
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import 取桌面路径

    return {"path": 取桌面路径()}


@应用.get("/api/default-bili-pc-cache-path")
async def 默认缓存路径接口() -> dict[str, str]:
    r"""
    获取默认哔哩哔哩桌面端缓存路径
    :return: dict[str, str]: 路径信息
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import 取默认哔哩电脑缓存路径

    return {"path": 取默认哔哩电脑缓存路径()}


@应用.get("/api/default-export-path")
async def 默认导出路径接口() -> dict[str, str]:
    r"""获取与当前操作系统匹配的默认导出根目录。"""
    from mybiout.pages.ohmyconfig.ohmyconfig import 取默认导出路径

    return {"path": 取默认导出路径()}


@应用.get("/api/localout/state")
async def 本地导出状态() -> dict[str, 任意]:
    r"""
    获取 LocalOut 当前状态快照
    :return: dict[str, Any]: 状态数据
    """
    from mybiout.pages.localout.localout import 取状态

    return 取状态()


@应用.get("/api/localout/env-status")
async def 本地导出环境状态() -> dict[str, 任意]:
    r"""
    获取环境状态信息（ADB、FFmpeg 等）
    :return: dict[str, Any]: 环境状态
    """
    from mybiout.pages.localout.localout import 取环境状态

    return 取环境状态()


@应用.get("/api/localout/available-sources")
async def 本地导出可用来源() -> dict[str, 任意]:
    r"""
    获取可用的扫描源列表和环境警告
    :return: dict[str, Any]: 包含 sources 和 warnings
    """
    from mybiout.pages.localout.localout import 取可用来源

    return 取可用来源()


@应用.post("/api/localout/browse-local")
def 本地导出浏览本地() -> dict[str, bool | str]:
    r"""
    弹出文件夹对话框选择本地缓存目录
    :return: dict[str, bool | str]: 选择结果
    """
    from mybiout.pages.localout.localout import 浏览本地

    目录路径: str | None = 浏览本地()
    return {"ok": True, "path": 目录路径} if 目录路径 else {"ok": False}


@应用.post("/api/localout/restore/browse")
def 本地导出浏览恢复归档() -> dict[str, bool | str]:
    r"""选择一个归档或包含多个归档的上级文件夹。"""
    from mybiout.pages.localout.localout import 浏览恢复归档

    目录路径: str | None = 浏览恢复归档()
    return {"ok": True, "path": 目录路径} if 目录路径 else {"ok": False}


@应用.post("/api/localout/restore/scan")
async def 本地导出扫描恢复归档(请求对象: 请求) -> dict[str, 任意]:
    r"""递归发现目录中的有效恢复归档，不依赖导出索引。"""
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)

    from mybiout.pages.localout.localout import 扫描恢复归档

    return 扫描恢复归档(_转字符串(请求体.get("path", "")))


@应用.post("/api/localout/restore/inspect")
async def 本地导出检查恢复归档(请求对象: 请求) -> dict[str, 任意]:
    r"""检查恢复归档并返回标题与目标缓存路径。"""
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)

    from mybiout.pages.localout.localout import 检查恢复归档

    return 检查恢复归档(_转字符串(请求体.get("path", "")))


@应用.get("/api/localout/restore/devices")
async def 本地导出恢复设备列表() -> dict[str, 任意]:
    r"""获取可接收恢复缓存的 ADB 设备及客户端。"""
    from mybiout.pages.localout.localout import 取恢复设备列表

    return 取恢复设备列表()


@应用.post("/api/localout/restore/start")
async def 本地导出开始恢复(请求对象: 请求) -> dict[str, 任意]:
    r"""启动单项或批量归档重建与手机导入任务。"""
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)

    from mybiout.pages.localout.localout import 开始批量恢复

    路径列表 = _转字符串列表(请求体.get("paths", []))
    if not 路径列表 and 请求体.get("path") is not None:
        路径列表 = [_转字符串(请求体.get("path", ""))]
    return 开始批量恢复(
        归档路径列表=路径列表,
        序列号=_转字符串(请求体.get("serial", "")),
        包名=_转字符串(请求体.get("package", "")),
        缓存布局=_转字符串(请求体.get("layout", "")),
    )


@应用.post("/api/localout/restore/cancel")
async def 本地导出取消恢复() -> dict[str, 任意]:
    r"""请求停止后续批量恢复项目。"""
    from mybiout.pages.localout.localout import 取消恢复

    return 取消恢复()


@应用.post("/api/localout/add-source")
async def 本地导出添加来源(请求对象: 请求) -> dict[str, 任意]:
    r"""
    添加扫描源
    :param: 请求对象: 请求对象, body 包含 source_type/path/label/serial/package
    :return: dict[str, Any]: 添加结果
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)

    from mybiout.pages.localout.localout import 添加来源

    return 添加来源(
        来源类型=_转字符串(请求体.get("source_type", "")),
        路径文本=_转字符串(请求体.get("path", "")),
        标签=_转字符串(请求体.get("label", "")),
        序列号=_转字符串(请求体.get("serial", "")),
        包名=_转字符串(请求体.get("package", "")),
    )


@应用.post("/api/localout/pause-scan")
async def 本地导出暂停扫描() -> dict[str, bool]:
    r"""
    暂停当前扫描
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import 暂停扫描

    暂停扫描()
    return {"ok": True}


@应用.post("/api/localout/resume-scan")
async def 本地导出继续扫描() -> dict[str, bool]:
    r"""
    恢复暂停的扫描
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import 继续扫描

    继续扫描()
    return {"ok": True}


@应用.post("/api/localout/cancel-scan")
async def 本地导出取消扫描() -> dict[str, bool]:
    r"""
    取消当前扫描
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import 取消扫描

    取消扫描()
    return {"ok": True}


@应用.post("/api/localout/add-to-tasks")
async def 本地导出加入任务(请求对象: 请求) -> dict[str, 任意]:
    r"""
    将源卡片添加到任务栏
    :param: 请求对象: 请求对象, body 包含 card_ids
    :return: dict[str, Any]: 添加结果
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    卡片编号列表: list[str] = _转字符串列表(请求体.get("card_ids", []))

    from mybiout.pages.localout.localout import 加入任务

    return 加入任务(卡片编号列表)


@应用.post("/api/localout/remove-source")
async def 本地导出移除来源(请求对象: 请求) -> dict[str, bool]:
    r"""
    移除指定源卡片
    :param: 请求对象: 请求对象, body 包含 card_ids
    :return: dict[str, bool]: 操作结果
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    卡片编号列表: list[str] = _转字符串列表(请求体.get("card_ids", []))

    from mybiout.pages.localout.localout import 移除来源卡片

    移除来源卡片(卡片编号列表)
    return {"ok": True}


@应用.post("/api/localout/remove-tasks")
async def 本地导出移除任务(请求对象: 请求) -> dict[str, bool]:
    r"""
    移除指定任务卡片
    :param: 请求对象: 请求对象, body 包含 card_ids
    :return: dict[str, bool]: 操作结果
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    卡片编号列表: list[str] = _转字符串列表(请求体.get("card_ids", []))

    from mybiout.pages.localout.localout import 移除任务卡片

    移除任务卡片(卡片编号列表)
    return {"ok": True}


@应用.post("/api/localout/clear-source")
async def 本地导出清空来源() -> dict[str, bool]:
    r"""
    清空源栏
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import 清空来源

    清空来源()
    return {"ok": True}


@应用.post("/api/localout/clear-tasks")
async def 本地导出清空任务() -> dict[str, bool]:
    r"""
    清空任务栏
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import 清空任务

    清空任务()
    return {"ok": True}


@应用.post("/api/localout/clear-completed")
async def 本地导出清空完成() -> dict[str, bool]:
    r"""
    清空完成栏
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import 清空完成

    清空完成()
    return {"ok": True}


@应用.post("/api/localout/start-export")
async def 本地导出开始导出(请求对象: 请求) -> dict[str, 任意]:
    r"""
    开始导出任务
    :param: 请求对象: 请求对象, body 包含 card_ids
    :return: dict[str, Any]: 导出结果
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    卡片编号列表: list[str] = _转字符串列表(请求体.get("card_ids", []))

    from mybiout.pages.localout.localout import 开始导出

    return 开始导出(卡片编号列表)


@应用.get("/api/localout/cover/{card_id}")
async def 本地导出封面(卡片编号: str = 路径参数(alias="card_id")) -> 响应:
    r"""
    返回指定卡片的封面图片
    """
    from mybiout.pages.localout.localout import 取封面字节

    if 结果 := 取封面字节(卡片编号):
        数据, 内容类型 = 结果
        return 响应(content=数据, media_type=内容类型, headers={"Cache-Control": "max-age=300"})
    return 响应(status_code=404)


@应用.post("/api/localout/cancel-export")
async def 本地导出取消导出() -> dict[str, bool]:
    r"""
    取消正在进行的导出
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.localout.localout import 取消导出

    取消导出()
    return {"ok": True}


@应用.get("/api/bbdown/state")
async def 下载状态() -> dict[str, 任意]:
    r"""
    获取 BBDown 当前状态快照
    :return: dict[str, Any]: 状态数据
    """
    from mybiout.pages.bbdown.bbdown import 取状态

    return 取状态()


@应用.get("/api/bbdown/env-check")
async def 下载环境检查() -> dict[str, 任意]:
    r"""
    检查 BBDown 运行环境
    :return: dict[str, Any]: 环境检测结果
    """
    from mybiout.pages.bbdown.bbdown import 环境检查

    return 环境检查()


@应用.post("/api/bbdown/add")
async def 下载添加任务(请求对象: 请求) -> 响应:
    r"""
    添加 BBDown 下载任务
    :param: 请求对象: 请求对象, body 包含 url/options
    :return: Response: JSON 响应, 成功 200, 失败 400
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    链接: str = _转字符串(请求体.get("url", ""))
    选项: 任意 = 请求体.get("options")

    from mybiout.pages.bbdown.bbdown import 添加任务

    结果: dict[str, 任意] = 添加任务(链接, 选项)
    状态码: int = 200 if bool(结果.get("ok")) else 400
    return 数据响应(status_code=状态码, content=结果)


@应用.post("/api/bbdown/cancel")
async def 下载取消当前() -> dict[str, bool]:
    r"""
    取消当前 BBDown 下载
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.bbdown.bbdown import 取消当前

    取消当前()
    return {"ok": True}


@应用.post("/api/bbdown/retry")
async def 下载重试任务(请求对象: 请求) -> dict[str, 任意]:
    r"""
    重试失败的 BBDown 任务
    :param: 请求对象: 请求对象, body 包含 task_id
    :return: dict[str, Any]: 操作结果
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    任务编号: str = _转字符串(请求体.get("task_id", ""))

    from mybiout.pages.bbdown.bbdown import 重试任务

    return 重试任务(任务编号)


@应用.post("/api/bbdown/remove")
async def 下载移除任务(请求对象: 请求) -> dict[str, bool]:
    r"""
    移除 BBDown 任务
    :param: 请求对象: 请求对象, body 包含 task_id
    :return: dict[str, bool]: 操作结果
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    任务编号: str = _转字符串(请求体.get("task_id", ""))

    from mybiout.pages.bbdown.bbdown import 移除任务

    移除任务(任务编号)
    return {"ok": True}


@应用.post("/api/bbdown/clear-completed")
async def 下载清空完成() -> dict[str, bool]:
    r"""
    清空 BBDown 已完成列表
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.bbdown.bbdown import 清空完成

    清空完成()
    return {"ok": True}


@应用.post("/api/bbdown/clear-failed")
async def 下载清空失败() -> dict[str, bool]:
    r"""
    清空 BBDown 失败任务
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.bbdown.bbdown import 清空失败

    清空失败()
    return {"ok": True}


@应用.post("/api/bbdown/clear-queue")
async def 下载清空队列() -> dict[str, bool]:
    r"""
    清空 BBDown 排队任务
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.bbdown.bbdown import 清空队列

    清空队列()
    return {"ok": True}


@应用.get("/api/mdout/state")
async def 文档导出状态() -> dict[str, 任意]:
    r"""
    获取 MdOut 当前状态快照
    :return: dict[str, Any]: 状态数据
    """
    from mybiout.pages.mdout.mdout import 取状态

    return 取状态()


@应用.post("/api/mdout/parse")
async def 文档导出解析(请求对象: 请求) -> dict[str, 任意]:
    r"""
    解析输入文本识别类型
    :param: 请求对象: 请求对象, body 包含 text
    :return: dict[str, Any]: 解析结果
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    文本: str = _转字符串(请求体.get("text", ""))

    from mybiout.pages.mdout.mdout import 执行解析

    return 执行解析(文本)


@应用.post("/api/mdout/add")
async def 文档导出添加(请求对象: 请求) -> 响应:
    r"""
    添加 MdOut 获取任务
    :param: 请求对象: 请求对象, body 包含 text
    :return: Response: JSON 响应, 成功 200, 失败 400
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    文本: str = _转字符串(请求体.get("text", ""))
    期望类型: str = _转字符串(请求体.get("expect_type", "")).strip()

    from mybiout.pages.mdout.mdout import 添加并获取

    结果: dict[str, 任意] = 添加并获取(文本, 期望类型=期望类型 or None)
    状态码: int = 200 if bool(结果.get("ok")) else 400
    return 数据响应(status_code=状态码, content=结果)


@应用.post("/api/mdout/select")
async def 文档导出选择(请求对象: 请求) -> dict[str, bool]:
    r"""
    选中 MdOut 卡片以预览
    :param: 请求对象: 请求对象, body 包含 card_id
    :return: dict[str, bool]: 操作结果
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    卡片编号: str = _转字符串(请求体.get("card_id", ""))

    from mybiout.pages.mdout.mdout import 选择卡片

    选择卡片(卡片编号)
    return {"ok": True}


@应用.post("/api/mdout/export")
async def 文档导出执行(请求对象: 请求) -> dict[str, 任意]:
    r"""
    导出指定 MdOut 卡片
    :param: 请求对象: 请求对象, body 包含 card_ids
    :return: dict[str, Any]: 导出结果
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    卡片编号列表: list[str] = _转字符串列表(请求体.get("card_ids", []))

    from mybiout.pages.mdout.mdout import 导出卡片

    return 导出卡片(卡片编号列表)


@应用.post("/api/mdout/export-all")
async def 文档导出全部() -> dict[str, 任意]:
    r"""
    导出全部就绪的 MdOut 卡片
    :return: dict[str, Any]: 导出结果
    """
    from mybiout.pages.mdout.mdout import 导出全部就绪

    return 导出全部就绪()


@应用.post("/api/mdout/remove")
async def 文档导出移除(请求对象: 请求) -> dict[str, bool]:
    r"""
    移除指定 MdOut 卡片
    :param: 请求对象: 请求对象, body 包含 card_ids
    :return: dict[str, bool]: 操作结果
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    卡片编号列表: list[str] = _转字符串列表(请求体.get("card_ids", []))

    from mybiout.pages.mdout.mdout import 移除卡片

    移除卡片(卡片编号列表)
    return {"ok": True}


@应用.post("/api/mdout/clear")
async def 文档导出清空() -> dict[str, bool]:
    r"""
    清空全部 MdOut 卡片
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.mdout.mdout import 清空卡片

    清空卡片()
    return {"ok": True}


@应用.post("/api/mdout/clear-completed")
async def 文档导出清空完成() -> dict[str, bool]:
    r"""
    清空 MdOut 已完成列表
    :return: dict[str, bool]: 操作结果
    """
    from mybiout.pages.mdout.mdout import 清空完成

    清空完成()
    return {"ok": True}


@应用.post("/api/man/chat")
async def 手册对话(请求对象: 请求) -> dict[str, 任意]:
    r"""
    Man 页面 AI 对话接口
    :param: 请求对象: 请求对象, body 包含 prompt 和可选 force_bs
    :return: dict[str, Any]: 对话结果, 包含 reply/source/note
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    提示词: str = _转字符串(请求体.get("prompt", ""))
    直接说: bool = bool(请求体.get("force_bs", False))

    from mybiout.pages.man.man import 对话

    return 对话(提示词, 直接说=直接说)


@应用.post("/api/parse-batch")
async def 解析批量输入接口(请求对象: 请求) -> dict[str, 任意]:
    r"""
    将混排粘贴拆成条目, 并给出每行一条的回填文本。
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    文本: str = _转字符串(请求体.get("text", ""))
    from mybiout.pages.batch_input import 构建批量文本
    from mybiout.pages.batch_input import 解析批量输入

    项们: list[str] = 解析批量输入(文本)
    return {"ok": True, "items": 项们, "built": 构建批量文本(项们)}


@应用.post("/api/open-explorer")
async def 打开资源管理器接口(请求对象: 请求) -> dict[str, bool | str]:
    r"""
    在资源管理器中定位文件
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    路径文本: str = _转字符串(请求体.get("path", ""))

    from mybiout.pages.bbdown.bbdown import 在资源管理器中打开

    return 在资源管理器中打开(路径文本)


@应用.post("/api/qrcode/generate")
async def 生成登录二维码接口() -> dict[str, 任意]:
    r"""
    生成扫码登录二维码 (B 站官方 passport 接口, 无风控风险)
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import 生成登录二维码

    return 生成登录二维码()


@应用.get("/api/bilibili-login-status")
async def B站登录态检查接口() -> dict[str, 任意]:
    r"""
    只读检查当前保存的 B 站登录态是否有效。
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import 检查B站登录态

    return 检查B站登录态()


@应用.post("/api/qrcode/poll")
async def 轮询扫码登录接口(请求对象: 请求) -> dict[str, 任意]:
    r"""
    轮询扫码登录状态, 成功时返回 SESSDATA
    """
    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    二维码键: str = _转字符串(请求体.get("qrcode_key", ""))
    if not 二维码键:
        return {"status": "error", "error": "缺少 qrcode_key"}

    from mybiout.pages.ohmyconfig.ohmyconfig import 轮询扫码登录

    return 轮询扫码登录(二维码键)


@应用.post("/api/reset-all-settings")
async def 重置全部设置接口() -> dict[str, bool]:
    r"""
    恢复全部默认设置
    """
    from mybiout.pages.ohmyconfig.ohmyconfig import 重置全部

    return 重置全部()


@应用.post("/api/mdout/open-folder")
async def 文档导出打开目录() -> dict[str, bool | str]:
    r"""
    打开 MdOut 导出目录
    """
    from mybiout.pages.bbdown.bbdown import 在资源管理器中打开
    from mybiout.pages.mdout.mdout import 取导出文件夹路径

    return 在资源管理器中打开(取导出文件夹路径())


@应用.post("/api/man/chat-stream")
async def 手册流式对话(请求对象: 请求):
    r"""
    Man 页面 AI 流式对话接口 (SSE)
    """
    from fastapi.responses import StreamingResponse

    请求体: dict[str, 任意] = await _读取数据字典(请求对象)
    提示词: str = _转字符串(请求体.get("prompt", ""))
    直接说: bool = bool(请求体.get("force_bs", False))

    from mybiout.pages.man.man import 流式对话SSE

    return StreamingResponse(
        流式对话SSE(提示词, 直接说=直接说),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
