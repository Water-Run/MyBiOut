r"""
MyBiOut! 设置页服务层, 负责设置的校验、浏览与业务逻辑

:file: mybiout/pages/ohmyconfig/ohmyconfig.py
:author: WaterRun
:time: 2026-04-07
"""

from pathlib import Path as 路径
from urllib.parse import parse_qs as 解析查询
from urllib.parse import urlparse as 拆分网址

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


_哔哩请求头: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com",
}


def 生成登录二维码() -> dict:
    r"""
    调用 B 站官方 passport 接口生成扫码登录二维码

    走官方网页扫码登录流程 (与 BBDown 等同款): 不碰密码/短信/滑块,
    正常浏览器请求头 + 低频轮询, 无风控风险。
    :return: dict: {ok, qrcode_key, qr_svg} 或 {ok: False, error}
    """
    try:
        import io as 输入输出

        import httpx as 网络请求
        import qrcode as 二维码库
        import qrcode.image.svg as 二维码矢量
    except ImportError:
        return {"ok": False, "error": "缺少依赖 (httpx / qrcode), 绿色包应自带"}

    try:
        with 网络请求.Client(headers=_哔哩请求头, timeout=15.0) as 客户端:
            响应 = 客户端.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate")
        数据: dict = 响应.json()
        if 数据.get("code") != 0:
            return {"ok": False, "error": f"生成二维码失败: {数据.get('message', '未知错误')}"}
        扫码内容: str = 数据["data"]["url"]
        二维码键: str = 数据["data"]["qrcode_key"]

        图像 = 二维码库.make(扫码内容, image_factory=二维码矢量.SvgPathImage, box_size=10, border=2)
        缓冲 = 输入输出.BytesIO()
        图像.save(缓冲)
        return {"ok": True, "qrcode_key": 二维码键, "qr_svg": 缓冲.getvalue().decode("utf-8")}
    except Exception as 异常:
        return {"ok": False, "error": f"生成二维码异常: {异常}"}


def 轮询扫码登录(二维码键: str) -> dict:
    r"""
    轮询扫码登录状态 (官方接口, 前端低频调用即可)
    :param: 二维码键: qrcode_key
    :return: dict: {status: waiting/scanned/success/expired/error, sessdata?}
    """
    try:
        import httpx as 网络请求
    except ImportError:
        return {"status": "error", "error": "缺少 httpx 依赖, 绿色包应自带"}

    try:
        with 网络请求.Client(headers=_哔哩请求头, timeout=15.0) as 客户端:
            响应 = 客户端.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                params={"qrcode_key": 二维码键},
            )
        数据: dict = 响应.json()
        if 数据.get("code") != 0:
            return {"status": "error", "error": 数据.get("message", "轮询失败")}
        载荷: dict = 数据.get("data") or {}
        状态码 = 载荷.get("code")
        if 状态码 == 0:
            查询: dict = 解析查询(拆分网址(载荷.get("url", "")).query)
            会话值: str = (查询.get("SESSDATA") or [""])[0]
            if not 会话值:
                # 兜底: 从 Set-Cookie 里取
                for 饼干头 in 响应.headers.get_list("set-cookie"):
                    if 饼干头.startswith("SESSDATA="):
                        会话值 = 饼干头.split(";", 1)[0].split("=", 1)[1]
                        break
            if not 会话值:
                return {"status": "error", "error": "登录成功但未取到 SESSDATA"}
            return {"status": "success", "sessdata": 会话值}
        if 状态码 == 86090:
            return {"status": "scanned"}
        if 状态码 == 86101:
            return {"status": "waiting"}
        if 状态码 == 86038:
            return {"status": "expired"}
        return {"status": "error", "error": f"未知状态: {载荷.get('message', 状态码)}"}
    except Exception as 异常:
        return {"status": "error", "error": f"轮询异常: {异常}"}
