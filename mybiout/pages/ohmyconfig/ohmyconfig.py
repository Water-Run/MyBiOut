r"""
MyBiOut! 设置页服务层, 负责设置的校验、浏览与业务逻辑

:file: mybiout/pages/ohmyconfig/ohmyconfig.py
:author: WaterRun
:time: 2026-04-07
"""

from contextlib import suppress as 忽略异常
from pathlib import Path as 路径

from mybiout.pages import utils as 工具

type 设置结果 = dict[str, bool | str]

_允许布尔值: set[str] = {"true", "false"}
_允许缺失标题处理: set[str] = {"partial_or_folder", "folder_only", "skip"}
_允许命名部件: set[str] = {"bv", "title", "up", "group", "part", "publish_time", "export_time"}
_允许收藏夹详情: set[str] = {"basic", "full"}
_允许请求间隔: set[str] = {"0.3", "0.5", "1.0", "2.0"}
_允许接口超时: set[str] = {"infinite", "8s", "20s", "60s", "100s", "1000s"}


def 取设置() -> dict[str, dict[str, str]]:
    r"""
    获取全部设置项
    :return: dict[str, dict[str, str]]: 全部设置
    """
    return 工具.取全部设置()


def 校验并保存(分区: str, 键: str, 值: str) -> 设置结果:
    r"""
    校验后保存单条设置
    :param: 分区: 配置分区名
    :param: 键: 配置键名
    :param: 值: 配置值
    :return: 设置结果: 包含 ok 和可选 error 的结果字典
    """
    match (分区, 键):
        case ("export", "path"):
            if not 值.strip():
                return _失败("路径不能空着啊!")
            工具.设设置(分区, 键, 值.strip())
            return _成功()

        case ("localout" | "bbdown" | "mdout", "folder"):
            return _校验文件夹(分区, 值)

        case ("localout", "bilibili_pc_cache_optional_when_installed"):
            return _保存布尔(分区, 键, 值)

        case ("localout", "bilibili_pc_cache_path"):
            工具.设设置(分区, 键, 值.strip())
            return _成功()

        case ("localout", "ffmpeg_concurrent"):
            规范值 = 值.strip()
            if not 规范值.isdigit() or not (1 <= int(规范值) <= 32):
                return _失败("ffmpeg并发范围建议 1~32")
            工具.设设置(分区, 键, 规范值)
            return _成功()

        case ("localout", "name_parts"):
            部件列表: list[str] = [项.strip() for 项 in 值.split(",") if 项.strip()]
            if not 部件列表:
                return _失败("命名至少勾一个吧!")
            if 未知项 := [项 for 项 in 部件列表 if 项 not in _允许命名部件]:
                return _失败(f"出现了未知命名项: {', '.join(未知项)}")
            工具.设设置(分区, 键, ",".join(部件列表))
            return _成功()

        case ("localout", "incomplete_title_action"):
            规范值 = 值.strip()
            if 规范值 not in _允许缺失标题处理:
                return _失败("标题补全策略值不合法")
            工具.设设置(分区, 键, 规范值)
            return _成功()

        case ("localout", "crawler_fallback"):
            规范值 = 值.strip().lower()
            if 规范值 not in {"disabled", "1s", "2s", "5s"}:
                return _失败("爬虫超时选项只能为 disabled / 1s / 2s / 5s")
            工具.设设置(分区, 键, 规范值)
            return _成功()

        case ("bbdown", "download_danmaku" | "skip_subtitle" | "skip_cover" | "use_aria2c"):
            return _保存布尔(分区, 键, 值)

        case ("bbdown", "cookie"):
            工具.设设置(分区, 键, 值.strip())
            return _成功()

        case ("bbdown", "encoding_priority" | "quality_priority" | "file_pattern" | "multi_file_pattern"):
            工具.设设置(分区, 键, 值.strip())
            return _成功()

        case ("mdout", "include_cover" | "include_tags" | "include_stats"):
            return _保存布尔(分区, 键, 值)

        case ("mdout", "sessdata"):
            工具.设设置(分区, 键, 值.strip())
            return _成功()

        case ("mdout", "favorite_detail"):
            规范值 = 值.strip()
            if 规范值 not in _允许收藏夹详情:
                return _失败("收藏夹详情只能是 basic / full")
            工具.设设置(分区, 键, 规范值)
            return _成功()

        case ("mdout", "request_delay"):
            规范值 = 值.strip()
            if 规范值 not in _允许请求间隔:
                return _失败("请求间隔只能是 0.3 / 0.5 / 1.0 / 2.0")
            工具.设设置(分区, 键, 规范值)
            return _成功()

        case ("api", "enabled"):
            规范值 = 值.strip().lower()
            if 规范值 in {"1", "true", "yes", "on", "启用"}:
                工具.设设置(分区, 键, "true")
            else:
                工具.设设置(分区, 键, "false")
            return _成功()

        case ("api", "key" | "model"):
            工具.设设置(分区, 键, 值.strip())
            return _成功()

        case ("api", "base_url"):
            规范值: str = 值.strip()
            if not 规范值:
                return _失败("API 地址不能为空")
            if not (规范值.startswith("http://") or 规范值.startswith("https://")):
                return _失败("API 地址需以 http:// 或 https:// 开头")
            工具.设设置(分区, 键, 规范值.rstrip("/"))
            return _成功()

        case ("api", "timeout"):
            规范值: str = 值.strip().lower()
            if 规范值 not in _允许接口超时:
                return _失败("超时选项不合法")
            工具.设设置(分区, 键, 规范值)
            return _成功()

        case _:
            工具.设设置(分区, 键, str(值))
            return _成功()


def _保存布尔(分区: str, 键: str, 值: str) -> 设置结果:
    r"""
    校验并保存布尔型设置
    :param: 分区: 配置分区名
    :param: 键: 配置键名
    :param: 值: 待校验值
    :return: 设置结果: 保存结果
    """
    规范值: str = 值.strip().lower()
    if 规范值 not in _允许布尔值:
        return _失败("开关值不对劲, 只能 true/false")
    工具.设设置(分区, 键, 规范值)
    return _成功()


def _校验文件夹(分区: str, 值: str) -> 设置结果:
    r"""
    校验并保存文件夹名称, 检查冲突
    :param: 分区: 配置分区名
    :param: 值: 文件夹名称
    :return: 设置结果: 保存结果
    """
    名称: str = 值.strip()
    if not 名称:
        return _失败("文件夹名不能空着!")

    for 其他分区 in ("localout", "bbdown", "mdout"):
        if 其他分区 != 分区 and 工具.取设置(其他分区, "folder") == 名称:
            return _失败(f"和 {其他分区} 的撞了!")

    导出路径文本: str = 工具.取设置("export", "path").strip()
    if 导出路径文本:
        try:
            导出目录: 路径 = 路径(导出路径文本)
            if 导出目录.exists():
                已占用名称: set[str] = {工具.取设置(当前分区, "folder") for 当前分区 in ("localout", "bbdown", "mdout")}
                for 条目 in 导出目录.iterdir():
                    if 条目.is_dir() and 条目.name == 名称 and 条目.name not in 已占用名称:
                        return _失败(f"那里已经有叫 '{名称}' 的了!")
        except Exception:
            pass

    工具.设设置(分区, "folder", 名称)
    return _成功()


def 浏览文件夹() -> str | None:
    r"""
    弹出系统文件夹选择对话框
    :return: str | None: 选中的路径, 取消时返回 None
    """
    try:
        from tkinter import Tk as 窗口
        from tkinter import filedialog as 文件对话框

        根窗口: 窗口 = 窗口()
        根窗口.withdraw()
        根窗口.attributes("-topmost", True)
        文件夹: str = 文件对话框.askdirectory(title="选一个地方放东西")
        根窗口.destroy()
        return 文件夹 if 文件夹 else None
    except Exception:
        return None


def 取桌面路径() -> str:
    r"""
    获取桌面下的 MyBiOut! 路径
    :return: str: 桌面导出路径
    """
    return str(路径.home() / "Desktop" / "MyBiOut!")


def 取默认哔哩电脑缓存路径() -> str:
    r"""
    获取默认哔哩哔哩电脑端缓存路径
    :return: str: 默认缓存路径
    """
    return 工具.取默认哔哩哔哩电脑缓存路径()


def _成功() -> 设置结果:
    r"""
    构建成功结果
    :return: 设置结果: 成功结果字典
    """
    return {"ok": True}


def _失败(消息: str) -> 设置结果:
    r"""
    构建失败结果
    :param: 消息: 错误信息
    :return: 设置结果: 失败结果字典
    """
    return {"ok": False, "error": 消息}


def 重置全部() -> dict[str, bool]:
    r"""
    恢复全部默认设置
    :return: dict: 操作结果
    """
    工具.重置全部设置()
    return {"ok": True}


def 通过登录自动取会话数据(用户代理: str | None = None, 超时秒数: int = 180) -> str | None:
    r"""
    打开可视化登录页，引导用户登录后自动读取 SESSDATA。
    使用持久化的浏览器用户资料目录，避免每次都打开全新的隐私窗口需要重新登录。
    """
    try:
        import time as 时间

        from playwright.sync_api import sync_playwright as 同步浏览器控制  # type: ignore
    except Exception:
        return None

    浏览器类型 = "chromium"
    浏览器通道 = None
    if 用户代理:
        小写代理 = 用户代理.lower()
        if "edg/" in 小写代理 or "edge" in 小写代理:
            浏览器类型 = "chromium"
            浏览器通道 = "msedge"
        elif "firefox" in 小写代理:
            浏览器类型 = "firefox"
        elif "chrome" in 小写代理:
            if not any(标记 in 小写代理 for 标记 in ["edg/", "edge", "opr/", "opera", "vivaldi", "brave"]):
                浏览器类型 = "chromium"
                浏览器通道 = "chrome"

    资料目录 = 工具.取资料目录()
    资料目录.mkdir(parents=True, exist_ok=True)
    资料目录文本 = str(资料目录)

    try:
        with 同步浏览器控制() as 浏览器控制:
            上下文 = None
            if 浏览器类型 == "firefox":
                with 忽略异常(Exception):
                    上下文 = 浏览器控制.firefox.launch_persistent_context(
                        user_data_dir=资料目录文本,
                        headless=False,
                        viewport={"width": 1280, "height": 800},
                    )

            if 上下文 is None:
                try:
                    上下文 = 浏览器控制.chromium.launch_persistent_context(
                        user_data_dir=资料目录文本,
                        channel=浏览器通道,
                        headless=False,
                        viewport={"width": 1280, "height": 800},
                    )
                except Exception:
                    上下文 = 浏览器控制.chromium.launch_persistent_context(
                        user_data_dir=资料目录文本,
                        headless=False,
                        viewport={"width": 1280, "height": 800},
                    )

            页面 = 上下文.new_page()
            页面.goto("https://www.bilibili.com", wait_until="domcontentloaded")

            with 忽略异常(Exception):
                页面.evaluate(
                    """() => {
                        const d=document.createElement('div');
                        d.style.cssText='position:fixed;z-index:999999;top:10px;left:10px;padding:8px 12px;background:#fb7299;color:#fff;font-size:14px;border-radius:6px;font-family:sans-serif;box-shadow:0 2px 10px rgba(0,0,0,0.2);';
                        d.textContent='请在此窗口完成B站登录，登录成功后可自动关闭';
                        document.body.appendChild(d);
                    }"""
                )

            截止时间 = 时间.time() + max(30, 超时秒数)
            while 时间.time() < 截止时间:
                站点饼干 = 上下文.cookies("https://www.bilibili.com")
                for 饼干 in 站点饼干:
                    if 饼干.get("name") == "SESSDATA" and 饼干.get("value"):
                        会话值 = 饼干["value"]
                        上下文.close()
                        return 会话值
                时间.sleep(1.0)

            上下文.close()
    except Exception:
        return None
    return None


def 自动获取会话数据(用户代理: str | None = None) -> str | None:
    r"""
    打开可视化登录窗口引导用户登录后获取 SESSDATA。
    """
    return 通过登录自动取会话数据(用户代理=用户代理, 超时秒数=180)
