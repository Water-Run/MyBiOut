r"""
MyBiOut! 基础工具模块, 负责配置文件的读写、便携路径与通用方法

:file: mybiout/pages/utils.py
:author: WaterRun
:time: 2026-04-06
"""

import configparser as 配置解析器
import os as 系统
import sys as 系统信息
import tempfile as 临时文件
import threading as 线程
from contextlib import suppress as 忽略异常
from pathlib import Path as 路径

_默认端口: int = 23333
_配置锁: 线程.RLock = 线程.RLock()


def 是否冻结运行() -> bool:
    r"""
    判断是否处于 PyInstaller 等冻结打包环境
    :return: bool: 冻结运行返回 True
    """
    return bool(getattr(系统信息, "frozen", False)) or hasattr(系统信息, "_MEIPASS")


def 取运行根目录() -> 路径:
    r"""
    获取运行根目录 (绿色包为 exe 旁, 开发态为 mybiout 包目录)
    配置、auth_profile、旁路 bin 均相对此目录
    :return: Path: 运行根目录
    """
    if getattr(系统信息, "frozen", False):
        return 路径(系统信息.executable).resolve().parent
    return 路径(__file__).resolve().parent.parent


def 取资源根目录() -> 路径:
    r"""
    获取只读资源根目录 (pages / assets / 内置 bin)
    冻结态优先 sys._MEIPASS/mybiout, 开发态为包目录
    :return: Path: 资源根目录
    """
    临时解压目录 = getattr(系统信息, "_MEIPASS", None)
    if 临时解压目录:
        候选: 路径 = 路径(临时解压目录) / "mybiout"
        if 候选.is_dir():
            return 候选
        return 路径(临时解压目录)
    return 路径(__file__).resolve().parent.parent


def 取工具目录() -> 路径:
    r"""
    获取外部工具 bin 目录 (优先运行根旁路, 其次资源内置)
    :return: Path: bin 目录
    """
    旁路: 路径 = 取运行根目录() / "bin"
    if 旁路.is_dir():
        return 旁路
    return 取资源根目录() / "bin"


def 取页面目录() -> 路径:
    r"""
    获取 HTML 页面目录
    :return: Path: pages 目录
    """
    return 取资源根目录() / "pages"


def 取静态资源目录() -> 路径:
    r"""
    获取静态资源目录
    :return: Path: assets 目录
    """
    return 取资源根目录() / "assets"


def 取资料目录() -> 路径:
    r"""
    获取可写的浏览器登录资料目录 (Playwright 持久化)
    :return: Path: auth_profile 目录
    """
    return 取运行根目录() / "auth_profile"


# 模块级配置路径: 绿色版/开发态均落在运行根 (exe 旁或 mybiout/)
_配置路径: 路径 = 取运行根目录() / "config.ini"


def 取默认哔哩哔哩电脑缓存路径() -> str:
    r"""
    获取默认的哔哩哔哩电脑端缓存路径
    :return: str: 默认缓存路径
    """
    return str(路径.home() / "Videos" / "bilibili")


默认设置: dict[str, dict[str, str]] = {
    "export": {
        "path": r"C:\MyBiOut!",
        "sessdata": "",
        "bilibili_login_enabled": "false",
    },
    "api": {
        "enabled": "false",
        "key": "",
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com/v1",
        "timeout": "infinite",
    },
    "localout": {
        "folder": "localout!",
        "bilibili_pc_cache_path": 取默认哔哩哔哩电脑缓存路径(),
        "bilibili_pc_cache_optional_when_installed": "true",
        "name_parts": "title",
        "incomplete_title_action": "partial_or_folder",
        "ffmpeg_concurrent": "3",
        "crawler_fallback": "disabled",
    },
    "bbdown": {
        "folder": "bbdown!",
        "cookie": "",
        "encoding_priority": "",
        "quality_priority": "",
        "download_danmaku": "false",
        "skip_subtitle": "false",
        "skip_cover": "false",
        "file_pattern": "<videoTitle>",
        "multi_file_pattern": "<videoTitle>/[P<pageNumberWithZero>]<pageTitle>",
        "use_aria2c": "false",
    },
    "mdout": {
        "folder": "mdout!",
        "sessdata": "",
        "include_cover": "true",
        "include_tags": "true",
        "include_stats": "true",
        "favorite_detail": "basic",
        "request_delay": "0.5",
    },
}


def _当前配置路径() -> 路径:
    r"""
    读取当前配置路径。
    """
    return _配置路径


def _当前保存配置函数():
    r"""
    读取当前保存配置函数。
    """
    return 保存配置


def 载入配置() -> 配置解析器.ConfigParser:
    r"""
    读取配置文件, 不存在则使用默认值。
    旧版已保存 SESSDATA 但尚无登录态开关时，兼容为已启用，避免升级后认证能力突然失效。
    :return: configparser.ConfigParser: 加载后的配置解析器
    """
    配置: 配置解析器.ConfigParser = 配置解析器.ConfigParser(interpolation=None)
    for 分区, 键值表 in 默认设置.items():
        配置[分区] = dict(键值表)
    配置路径: 路径 = _当前配置路径()
    if 配置路径.exists():
        原始配置: 配置解析器.ConfigParser = 配置解析器.ConfigParser(interpolation=None)
        try:
            原始配置.read(配置路径, encoding="utf-8")
            旧版登录态: bool = (
                原始配置.has_section("export")
                and "bilibili_login_enabled" not in 原始配置["export"]
                and bool((原始配置["export"].get("sessdata") or "").strip())
            )
        except 配置解析器.Error:
            旧版登录态 = False
        配置.read(配置路径, encoding="utf-8")
        if 旧版登录态:
            配置["export"]["bilibili_login_enabled"] = "true"
    return 配置


def 保存配置(配置: 配置解析器.ConfigParser) -> None:
    r"""
    将配置写回文件
    :param: 配置: 配置解析器实例
    """
    配置路径: 路径 = _当前配置路径()
    配置路径.parent.mkdir(parents=True, exist_ok=True)
    文件描述符, 临时文件名 = 临时文件.mkstemp(
        prefix=f".{配置路径.name}.",
        suffix=".tmp",
        dir=str(配置路径.parent),
        text=True,
    )
    临时路径: 路径 = 路径(临时文件名)
    try:
        with 系统.fdopen(文件描述符, "w", encoding="utf-8") as 文件:
            文件.write("# MyBiOut! 配置文件\n\n")
            配置.write(文件)
        临时路径.replace(配置路径)
    except Exception:
        with 忽略异常(OSError):
            临时路径.unlink()
        raise


def 取全部设置() -> dict[str, dict[str, str]]:
    r"""
    获取全部设置, 按 section -> key -> value 组织
    :return: dict[str, dict[str, str]]: 全部设置项
    """
    配置: 配置解析器.ConfigParser = 载入配置()
    return {分区: dict(配置[分区]) for 分区 in 配置.sections()}


def 取设置(分区: str, 键: str) -> str:
    r"""
    获取单项设置值
    :param: 分区: 配置分区名
    :param: 键: 配置键名
    :return: str: 配置值, 不存在时返回默认值
    """
    配置: 配置解析器.ConfigParser = 载入配置()
    默认值: str = 默认设置.get(分区, {}).get(键, "")
    return 配置.get(分区, 键, fallback=默认值)


def _校验配置标识符(名称: str, *, 角色: str) -> None:
    r"""
    拒绝会破坏 INI 结构的分区名/键名 (换行、方括号、等号、空字节等)。
    """
    if not 名称 or not str(名称).strip():
        raise ValueError(f"配置{角色}不能为空")
    文本 = str(名称)
    if any(c in 文本 for c in ("\n", "\r", "\0", "[", "]", "=", "#", ";")):
        raise ValueError(f"配置{角色}含非法字符: {文本!r}")
    if any(c.isspace() for c in 文本):
        raise ValueError(f"配置{角色}不能含空白: {文本!r}")


def 设设置(分区: str, 键: str, 值: str) -> None:
    r"""
    保存单项设置值
    :param: 分区: 配置分区名
    :param: 键: 配置键名
    :param: 值: 配置值
    :raises ValueError: 分区/键含控制字符等非法内容时拒绝写入, 避免下次载入 ParsingError
    """
    _校验配置标识符(分区, 角色="分区")
    _校验配置标识符(键, 角色="键")
    文本值 = "" if 值 is None else str(值)
    # 值中的裸换行会破坏 INI 下一行解析; 折叠为空白
    if any(c in 文本值 for c in ("\n", "\r", "\0")):
        文本值 = (
            文本值.replace("\0", "")
            .replace("\r\n", " ")
            .replace("\n", " ")
            .replace("\r", " ")
        )
    with _配置锁:
        配置: 配置解析器.ConfigParser = 载入配置()
        if 分区 not in 配置:
            配置[分区] = {}
        配置[分区][键] = 文本值
        _当前保存配置函数()(配置)


def 取导出路径() -> 路径:
    r"""
    获取导出根路径, 不存在则自动创建
    :return: Path: 导出根目录
    """
    导出路径: 路径 = 路径(取设置("export", "path"))
    导出路径.mkdir(parents=True, exist_ok=True)
    return 导出路径


def 取接口是否启用() -> bool:
    r"""
    Man 页大模型是否已完整启用 (缺少 Key 或 Model 时一律走本地通道)
    """
    值 = (取设置("api", "enabled") or "false").strip().lower()
    if 值 not in {"1", "true", "yes", "on", "启用"}:
        return False
    return bool(取接口密钥().strip() and 取接口模型().strip())


def 取接口密钥() -> str:
    r"""
    获取 API Key
    :return: str: API Key 值
    """
    return 取设置("api", "key")


def 取接口模型() -> str:
    r"""
    获取 API 模型名称
    :return: str: 模型名称
    """
    return 取设置("api", "model")


def 规范化接口模型(模型: str) -> str:
    r"""
    将 DeepSeek 的常见展示名转换成 API 模型标识符。
    其他 OpenAI 兼容服务的模型名保持原样。
    """
    文本: str = (模型 or "").strip()
    if not 文本:
        return ""
    DeepSeek别名: dict[str, str] = {
        "deepseek v4 flash": "deepseek-v4-flash",
        "deepseek_v4_flash": "deepseek-v4-flash",
        "deepseek-v4-flash": "deepseek-v4-flash",
        "deepseek v4 pro": "deepseek-v4-pro",
        "deepseek_v4_pro": "deepseek-v4-pro",
        "deepseek-v4-pro": "deepseek-v4-pro",
    }
    return DeepSeek别名.get(文本.lower(), 文本)


def 取端口() -> int:
    r"""
    获取默认服务端口号
    :return: int: 端口号
    """
    return _默认端口


def 取接口基地址() -> str:
    r"""
    获取 API 基地址
    :return: str: API 基地址
    """
    return 取设置("api", "base_url") or "https://api.openai.com/v1"


def 取接口超时秒数() -> float | None:
    r"""
    获取 API 超时时间（秒）
    :return: float | None: None 仅表示显式 infinite; 未知/旧格式不静默落无限
    """
    模式: str = (取设置("api", "timeout") or "infinite").strip().lower()
    超时映射: dict[str, float | None] = {
        "infinite": None,
        "8s": 8.0,
        "20s": 20.0,
        "60s": 60.0,
        "100s": 100.0,
        "1000s": 1000.0,
    }
    if 模式 in 超时映射:
        return 超时映射[模式]
    # 兼容旧格式纯数字秒 (如 "60") 与 "60.0"
    if 模式.endswith("s") and 模式[:-1].replace(".", "", 1).isdigit():
        try:
            秒 = float(模式[:-1])
            if 秒 > 0:
                return 秒
        except ValueError:
            pass
    if 模式.replace(".", "", 1).isdigit():
        try:
            秒 = float(模式)
            if 秒 > 0:
                return 秒
        except ValueError:
            pass
    # 未知值: 回落安全默认 60s, 切勿 None (否则请求无限挂起)
    return 60.0


def 取会话数据() -> str:
    r"""
    获取已启用的统一 SESSDATA (优先共享设置, 兼容旧分区)
    :return: str: SESSDATA 值
    """
    if not 取B站登录态是否启用():
        return ""
    共享值: str = 取设置("export", "sessdata").strip()
    if 共享值:
        return 共享值
    # 兼容旧配置
    for 分区 in ("bbdown", "mdout"):
        旧值: str = 取设置(分区, "sessdata" if 分区 == "mdout" else "cookie").strip()
        if 旧值:
            return 旧值
    return ""


def 取B站登录态是否启用() -> bool:
    r"""
    判断 B 站登录态是否允许供下载和文档导出使用。
    凭证保存与实际使用分离，避免误带 Cookie 请求外部服务。
    """
    值: str = (取设置("export", "bilibili_login_enabled") or "false").strip().lower()
    return 值 in {"1", "true", "yes", "on", "启用"}


def 取爬虫兜底超时() -> float | None:
    r"""
    获取本地缓存元数据无法解析时, 通过爬虫补全的超时时间
    :return: float | None: None 表示禁用, 否则为秒数
    """
    模式: str = (取设置("localout", "crawler_fallback") or "disabled").strip().lower()
    return {"1s": 1.0, "2s": 2.0, "5s": 5.0}.get(模式)


def 重置全部设置() -> None:
    r"""
    将全部设置恢复为默认值
    """
    with _配置锁:
        配置: 配置解析器.ConfigParser = 配置解析器.ConfigParser(interpolation=None)
        for 分区, 键值表 in 默认设置.items():
            配置[分区] = dict(键值表)
        _当前保存配置函数()(配置)
