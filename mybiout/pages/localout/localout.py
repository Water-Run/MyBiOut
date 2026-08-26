r"""
LocalOut! 本地缓存导出服务层, 负责扫描、解析和导出本地视频缓存

:file: mybiout/pages/localout/localout.py
:author: WaterRun
:time: 2026-04-12
"""

from __future__ import annotations

import ctypes as 系统接口
import hashlib as 哈希
import json as 数据交换
import os as 系统
import re as 正则
import shlex as 命令行转义
import shutil as 文件工具
import subprocess as 子进程
import sys as 系统信息
import tempfile as 临时文件
import threading as 线程
import time as 时间
import uuid as 唯一编号
from concurrent.futures import ThreadPoolExecutor as 线程池执行器
from concurrent.futures import as_completed as 逐个完成
from contextlib import suppress as 忽略异常
from dataclasses import dataclass as 数据类
from dataclasses import field as 字段
from dataclasses import replace as 替换数据
from datetime import datetime as 日期时间
from pathlib import Path as 路径

from mybiout.pages import utils as 工具
from mybiout.pages.localout.restore import 缓存已存在错误
from mybiout.pages.localout.restore import 导入缓存到手机
from mybiout.pages.localout.restore import 扫描恢复归档目录 as _扫描恢复归档目录
from mybiout.pages.localout.restore import 检查恢复归档 as _检查恢复归档
from mybiout.pages.localout.restore import 重建缓存组

try:
    import httpx as 网络请求

    _有网络请求: bool = True
except Exception:
    网络请求 = None
    _有网络请求: bool = False

_哔哩包列表: list[tuple[str, str]] = [
    ("tv.danmaku.bili", "哔哩哔哩"),
    ("com.bilibili.app.blue", "哔哩哔哩概念版"),
    ("com.bilibili.app.in", "哔哩哔哩国际版"),
]
_哔哩包名表: dict[str, str] = dict(_哔哩包列表)

_爬虫请求头: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}

_清晰度映射: dict[int, str] = {
    127: "8K 超高清",
    126: "杜比视界",
    125: "HDR 真彩",
    120: "4K 超清",
    116: "1080P 60帧",
    112: "1080P 高码率",
    80: "1080P 高清",
    74: "720P 60帧",
    64: "720P 高清",
    32: "480P 清晰",
    16: "360P 流畅",
    6: "240P 极速",
}

_音频编码阈值: int = 30200

_子进程附加参数: dict = {}
if 系统信息.platform == "win32":
    _子进程附加参数["creationflags"] = 0x08000000

_封面缓存目录: 路径 = 路径(临时文件.gettempdir()) / "mybiout_covers"
_封面缓存目录.mkdir(parents=True, exist_ok=True)

_缓存元文件名: tuple[str, ...] = ("danmaku.xml", "entry.json", "index.json")
_导出索引文件名: str = ".mybiout-export-index.json"
_归档元数据文件名: str = ".mybiout-archive-metadata.json"
_导出警告日志文件名: str = "LocalOut导出警告.log"
_导出索引锁: 线程.RLock = 线程.RLock()
_导出警告日志锁: 线程.RLock = 线程.RLock()
_导出身份锁表锁: 线程.Lock = 线程.Lock()
_导出身份锁表: dict[str, 线程.Lock] = {}


# ===== ADB 工具 =====


def _寻找ADB() -> str | None:
    r"""
    查找 adb 可执行文件路径（参考 biliandout DeviceScanner.find_adb）
    优先程序 bin/ 旁路（绿色包随发），再 PATH / 常见 SDK 目录
    :return: str | None: 路径, 未找到返回 None
    """
    工具目录: 路径 = 工具.取工具目录()
    程序名: str = "adb.exe" if 系统信息.platform == "win32" else "adb"
    for 候选路径 in (
        工具目录 / 程序名,
        工具目录 / "platform-tools" / 程序名,
        工具目录 / "adb" / 程序名,
    ):
        if 候选路径.is_file():
            工具.确保文件可执行(候选路径)
            return str(候选路径)
    which路径 = 文件工具.which(程序名)
    if which路径:
        return which路径
    if 系统信息.platform == "win32":
        for 候选路径 in (
            路径(系统.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            路径(系统.environ.get("USERPROFILE", ""))
            / "AppData"
            / "Local"
            / "Android"
            / "Sdk"
            / "platform-tools"
            / "adb.exe",
            路径("C:/Android/sdk/platform-tools/adb.exe"),
            路径("C:/Program Files/Android/platform-tools/adb.exe"),
            路径("C:/Program Files (x86)/Android/platform-tools/adb.exe"),
            路径("C:/Program Files (x86)/Android SDK Platform-Tools/platform-tools/adb.exe"),
        ):
            if 候选路径.is_file():
                return str(候选路径)
    return None


def _寻找FFmpeg() -> str | None:
    r"""优先使用绿色包旁路 ffmpeg，开发态才回退 PATH。"""
    工具目录: 路径 = 工具.取工具目录()
    程序名: str = "ffmpeg.exe" if 系统信息.platform == "win32" else "ffmpeg"
    for 随包路径 in (
        工具目录 / 程序名,
        工具目录 / "ffmpeg" / 程序名,
        工具目录 / "ffmpeg" / "bin" / 程序名,
    ):
        if 随包路径.is_file():
            工具.确保文件可执行(随包路径)
            return str(随包路径)
    return 文件工具.which(程序名)


def _执行ADB(ADB路径: str, 序列号: str, *命令参数: str, 超时秒数: float = 10) -> 子进程.CompletedProcess:
    r"""
    执行 adb [-s serial] <args> 命令
    :param: adb: adb 可执行文件路径
    :param: serial: 设备序列号（为空时省略 -s 参数）
    :param: 命令参数: 后续命令参数
    :param: 超时秒数: 超时秒数
    :return: subprocess.CompletedProcess
    """
    命令: list[str] = [ADB路径]
    if 序列号:
        命令 += ["-s", 序列号]
    命令 += list(命令参数)
    return 子进程.run(
        命令,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=超时秒数,
        **_子进程附加参数,
    )


def _取ADB设备列表() -> list[tuple[str, str]]:
    r"""
    获取已通过 ADB 连接且授权的设备列表（参考 biliandout DeviceScanner.get_adb_devices）
    :return: list[tuple[str, str]]: [(序列号, 显示名称), ...]
    """
    设备列表: list[tuple[str, str]] = []
    ADB路径: str | None = _寻找ADB()
    if not ADB路径:
        return 设备列表
    try:
        执行结果: 子进程.CompletedProcess = _执行ADB(ADB路径, "", "devices", "-l", 超时秒数=8)
        if 执行结果.returncode != 0:
            return 设备列表
        for 行 in 执行结果.stdout.strip().splitlines()[1:]:
            if not 行.strip():
                continue
            部件: list[str] = 行.split()
            if len(部件) >= 2 and 部件[1] == "device":
                序列号: str = 部件[0]
                型号: str = "Android设备"
                for 片段 in 部件[2:]:
                    if 片段.startswith("model:"):
                        型号 = 片段.split(":", 1)[1].replace("_", " ")
                        break
                设备列表.append((序列号, f"{型号} ({序列号})"))
    except Exception:
        pass
    return 设备列表


def _取ADB已安装哔哩包(ADB路径: str, 序列号: str) -> list[tuple[str, str]]:
    r"""返回设备中实际安装的哔哩客户端；查询失败时保守展示全部可支持版本。"""
    try:
        结果: 子进程.CompletedProcess = _执行ADB(
            ADB路径, 序列号, "shell", "pm list packages", 超时秒数=10
        )
        if 结果.returncode == 0:
            已安装: set[str] = {
                行.strip().removeprefix("package:")
                for 行 in 结果.stdout.splitlines()
                if 行.strip().startswith("package:")
            }
            return [(包名, 名称) for 包名, 名称 in _哔哩包列表 if 包名 in 已安装]
    except Exception:
        pass
    return list(_哔哩包列表)


def _取电脑端缓存路径() -> list[路径]:
    r"""发现已存在的电脑端哔哩缓存；发布包无本机配置时也能显示默认客户端目录。"""
    配置路径: str = 工具.取设置("localout", "bilibili_pc_cache_path").strip()
    候选列表: list[路径] = [
        路径(配置路径) if 配置路径 else 路径(),
        路径(工具.取默认哔哩哔哩电脑缓存路径()),
    ]
    已见: set[str] = set()
    可用列表: list[路径] = []
    for 候选 in 候选列表:
        if not str(候选) or str(候选) == "." or not 候选.is_dir():
            continue
        try:
            键 = str(候选.resolve()).lower()
        except OSError:
            键 = str(候选.absolute()).lower()
        if 键 not in 已见:
            已见.add(键)
            可用列表.append(候选)
    return 可用列表


# ===== 通用工具 =====


def _生成编号() -> str:
    return 唯一编号.uuid4().hex[:12]


def _短时间() -> str:
    return 日期时间.now().strftime("%H:%M:%S")


def _完整时间() -> str:
    return 日期时间.now().strftime("%Y-%m-%d %H:%M:%S")


def _取卷标(盘符: str) -> str:
    r"""
    获取驱动器卷标
    :param: letter: 单个大写盘符字母
    :return: str: 卷标名称
    """
    if 系统信息.platform == "win32":
        缓冲: 系统接口.Array = 系统接口.create_unicode_buffer(261)
        try:
            返回值: int = 系统接口.windll.kernel32.GetVolumeInformationW(
                f"{盘符}:\\",
                缓冲,
                261,
                None,
                None,
                None,
                None,
                0,
            )
            if 返回值 and 缓冲.value:
                return 缓冲.value
        except Exception:
            pass
    return f"存储设备 ({盘符}:)"


def _清理文件名(名称: str) -> str:
    名称 = 正则.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", 名称).strip(". ")
    名称 = 名称[:200] if 名称 else "untitled"
    if 正则.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", 名称):
        名称 = f"_{名称}"
    return 名称


def _兆字节(字节数: int | float) -> float:
    return round(字节数 / 1048576, 1) if 字节数 else 0


def _安全整数(值: object, 默认值: int = 0) -> int:
    r"""容忍损坏缓存中的空串、None 和非数字字段。"""
    try:
        return int(值)
    except (TypeError, ValueError, OverflowError):
        return 默认值


def _安全文本(值: object) -> str:
    r"""将缓存元数据中的 None 和非字符串值规范为可安全处理的文本。"""
    return str(值 or "").strip()


# ===== 数据模型 =====


@数据类(slots=True)
class _元文件复制结果:
    文件名列表: list[str] = 字段(default_factory=list)
    警告列表: list[str] = 字段(default_factory=list)


@数据类(slots=True)
class 视频卡片:
    r"""
    视频缓存卡片数据模型, 表示一个被扫描到的缓存视频
    """

    编号: str = 字段(default_factory=_生成编号)
    标题: str = ""
    BV号: str = ""
    AV号: str = ""
    UP主名称: str = ""
    合集标题: str = ""
    分集序号: int = 1
    清晰度: str = ""
    分辨率: str = ""
    字节数: int = 0
    发布时间: str = ""
    文件夹名: str = ""
    来源标签: str = ""
    来源类型: str = ""
    设备序列号: str = ""
    视频路径: str = ""
    音频路径: str = ""
    封面路径: str = ""
    元文件路径表: dict[str, str] = 字段(default_factory=dict)
    输出路径: str = ""
    状态名: str = "queued"
    错误: str = ""
    警告: str = ""

    def __post_init__(自身) -> None:
        for 属性名 in (
            "标题",
            "BV号",
            "AV号",
            "UP主名称",
            "合集标题",
            "清晰度",
            "分辨率",
            "发布时间",
            "文件夹名",
            "来源标签",
            "来源类型",
            "设备序列号",
            "视频路径",
            "音频路径",
            "封面路径",
            "输出路径",
            "状态名",
            "错误",
            "警告",
        ):
            setattr(自身, 属性名, _安全文本(getattr(自身, 属性名)))
        自身.分集序号 = _安全整数(自身.分集序号, 1)
        自身.字节数 = _安全整数(自身.字节数)

    def 转字典(自身) -> dict:
        仍存在: bool = True
        if 自身.来源类型 in ("local", "pc", "drive") and 自身.视频路径:
            仍存在 = 路径(自身.视频路径).exists()
        if 自身.来源类型 == "adb" and 自身.视频路径:
            显示路径 = 自身.视频路径.rsplit("/", 1)[0]
        else:
            显示路径 = str(路径(自身.视频路径).parent if 自身.视频路径 else "")
        return {
            "id": 自身.编号,
            "title": 自身.标题,
            "bvid": 自身.BV号,
            "avid": 自身.AV号,
            "up_name": 自身.UP主名称,
            "group_title": 自身.合集标题,
            "part": 自身.分集序号,
            "quality": 自身.清晰度,
            "resolution": 自身.分辨率,
            "size_bytes": 自身.字节数,
            "size_mb": _兆字节(自身.字节数),
            "publish_time": 自身.发布时间,
            "folder_name": 自身.文件夹名,
            "source_label": 自身.来源标签,
            "source_type": 自身.来源类型,
            "cover_url": f"/api/localout/cover/{自身.编号}" if 自身.封面路径 else "",
            "metadata_files": sorted(自身.元文件路径表),
            "video_path": 自身.视频路径,
            "output_path": 自身.输出路径,
            "path_display": 自身.输出路径 or 显示路径,
            "alive": 仍存在,
            "status": 自身.状态名,
            "error": 自身.错误,
            "warning": 自身.警告,
        }

    def 克隆(自身) -> 视频卡片:
        return 替换数据(
            自身,
            编号=_生成编号(),
            元文件路径表=dict(自身.元文件路径表),
            状态名="queued",
            错误="",
            警告="",
            输出路径="",
        )


# ===== 全局状态 =====


class _本地状态:
    r"""
    LocalOut 全局运行状态管理
    """

    def __init__(自身) -> None:
        自身.锁: 线程.RLock = 线程.RLock()
        自身.来源卡片列表: list[视频卡片] = []
        自身.任务卡片列表: list[视频卡片] = []
        自身.完成卡片列表: list[视频卡片] = []
        自身.日志列表: list[dict] = []
        自身.扫描状态: str = "idle"
        自身.扫描进度: float = 0.0
        自身.导出状态: str = "idle"
        自身.导出进度: float = 0.0
        自身.导出总数: int = 0
        自身.导出完成数: int = 0
        自身.导出成功数: int = 0
        自身.导出跳过数: int = 0
        自身.导出失败数: int = 0
        自身.恢复状态: str = "idle"
        自身.恢复进度: float = 0.0
        自身.恢复消息: str = ""
        自身.恢复错误: str = ""
        自身.恢复目标路径: str = ""
        自身.恢复项目列表: list[dict] = []
        自身.恢复总数: int = 0
        自身.恢复完成数: int = 0
        自身.恢复成功数: int = 0
        自身.恢复跳过数: int = 0
        自身.恢复失败数: int = 0
        自身._扫描线程: 线程.Thread | None = None
        自身._扫描取消: 线程.Event = 线程.Event()
        自身._扫描暂停: 线程.Event = 线程.Event()
        自身._导出线程: 线程.Thread | None = None
        自身._导出取消: 线程.Event = 线程.Event()
        自身._恢复线程: 线程.Thread | None = None
        自身._恢复取消: 线程.Event = 线程.Event()
        自身._恢复上次消息: str = ""
        自身._已知键集合: set[str] = set()
        自身._可用键集合: set[str] = set()
        自身._输出占用集合: set[str] = set()
        自身._上次可用刷新: float = 0.0

    def 记录日志(自身, 级别: str, 消息: str) -> None:
        with 自身.锁:
            自身.日志列表.append({"time": _短时间(), "level": 级别, "msg": 消息})
            if len(自身.日志列表) > 500:
                自身.日志列表 = 自身.日志列表[-300:]

    def 快照(自身) -> dict:
        with 自身.锁:
            return {
                "source_cards": [卡片项.转字典() for 卡片项 in 自身.来源卡片列表],
                "task_cards": [卡片项.转字典() for 卡片项 in 自身.任务卡片列表],
                "completed_cards": [卡片项.转字典() for 卡片项 in 自身.完成卡片列表],
                "logs": list(自身.日志列表),
                "available_keys": sorted(自身._可用键集合),
                "scan_status": 自身.扫描状态,
                "scan_progress": round(自身.扫描进度, 3),
                "export_status": 自身.导出状态,
                "export_progress": round(自身.导出进度, 3),
                "export_total": 自身.导出总数,
                "export_done": 自身.导出完成数,
                "export_success": 自身.导出成功数,
                "export_skipped": 自身.导出跳过数,
                "export_failed": 自身.导出失败数,
                "restore_status": 自身.恢复状态,
                "restore_progress": round(自身.恢复进度, 3),
                "restore_message": 自身.恢复消息,
                "restore_error": 自身.恢复错误,
                "restore_target_path": 自身.恢复目标路径,
                "restore_items": [dict(项目) for 项目 in 自身.恢复项目列表],
                "restore_total": 自身.恢复总数,
                "restore_done": 自身.恢复完成数,
                "restore_success": 自身.恢复成功数,
                "restore_skipped": 自身.恢复跳过数,
                "restore_failed": 自身.恢复失败数,
            }

    def _去重键(自身, 卡片项: 视频卡片) -> str:
        # 含 device_serial 避免不同 ADB 设备的相同路径发生碰撞
        return f"{卡片项.来源类型}|{卡片项.设备序列号}|{卡片项.视频路径}|{卡片项.音频路径}"

    def 添加来源卡片(自身, 卡片项: 视频卡片) -> bool:
        键: str = 自身._去重键(卡片项)
        with 自身.锁:
            if 键 in 自身._已知键集合:
                return False
            自身._已知键集合.add(键)
            自身.来源卡片列表.append(卡片项)
            return True


状态: _本地状态 = _本地状态()


# ===== 解析 / 查找函数 =====


def _嵌套取值(数据: dict, *候选路径: tuple[str, ...]) -> object:
    for 键路径 in 候选路径:
        当前值: object = 数据
        for 键 in 键路径:
            if not isinstance(当前值, dict) or 键 not in 当前值:
                当前值 = None
                break
            当前值 = 当前值[键]
        if 当前值 not in (None, "", [], {}):
            return 当前值
    return ""


def _格式化元数据时间(值: object) -> str:
    if 值 in (None, ""):
        return ""
    try:
        时间戳 = float(值)
        if 时间戳 > 10_000_000_000:
            时间戳 /= 1000
        return 日期时间.fromtimestamp(时间戳).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return str(值) if isinstance(值, str) else ""


def _从入口路径推断标识(入口路径: 路径) -> str:
    r"""从 ``entry.json`` 的相邻目录中提取 AV 数字目录作为元数据回退。"""
    当前目录 = 入口路径.parent
    for _ in range(5):
        目录名 = 当前目录.name
        if 目录名.isdigit():
            return 目录名
        if 匹配 := 正则.fullmatch(r"(?i)av(\d+)", 目录名):
            return 匹配.group(1)
        if 当前目录.parent == 当前目录:
            break
        当前目录 = 当前目录.parent
    return ""


def _规范化入口元数据(数据: dict, 回退标识: str = "") -> dict:
    r"""归一化普通版、概念版、国际版及 UGC/PGC 的 entry.json 字段。"""
    总标题 = str(
        _嵌套取值(
            数据,
            ("title",),
            ("video_title",),
            ("videoTitle",),
            ("name",),
            ("ep", "season_title"),
            ("episode", "season_title"),
        )
        or ""
    )
    分集标题 = str(
        _嵌套取值(
            数据,
            ("page_data", "part"),
            ("pageData", "part"),
            ("ep", "long_title"),
            ("ep", "index_title"),
            ("ep", "title"),
            ("episode", "long_title"),
            ("episode", "index_title"),
            ("episode", "title"),
        )
        or ""
    )
    显式合集标题 = str(
        _嵌套取值(
            数据,
            ("group_title",),
            ("groupTitle",),
            ("season_title",),
            ("seasonTitle",),
            ("ep", "season_title"),
            ("episode", "season_title"),
        )
        or ""
    )
    标题 = 总标题 or 分集标题 or 回退标识
    合集标题 = 显式合集标题
    if 分集标题 and 总标题 and 分集标题.strip() != 总标题.strip():
        标题 = 分集标题
        合集标题 = 合集标题 or 总标题

    BV号 = str(
        _嵌套取值(
            数据,
            ("bvid",),
            ("bv_id",),
            ("bvId",),
            ("page_data", "bvid"),
            ("pageData", "bvid"),
            ("ep", "bvid"),
            ("episode", "bvid"),
        )
        or ""
    )
    AV原值 = _嵌套取值(
        数据,
        ("avid",),
        ("aid",),
        ("av_id",),
        ("page_data", "avid"),
        ("page_data", "aid"),
        ("pageData", "avid"),
        ("pageData", "aid"),
        ("ep", "avid"),
        ("ep", "aid"),
        ("ep", "av_id"),
        ("episode", "avid"),
        ("episode", "aid"),
        ("episode", "av_id"),
    )
    AV号 = str(AV原值) if AV原值 not in (None, "") else (
        回退标识 if 回退标识.isdigit() else ""
    )
    if 匹配 := 正则.fullmatch(r"(?i)av(\d+)", AV号):
        AV号 = 匹配.group(1)
    UP主名称 = str(
        _嵌套取值(
            数据,
            ("owner_name",),
            ("up_name",),
            ("upName",),
            ("uname",),
            ("author",),
            ("owner", "name"),
            ("upper", "name"),
            ("up", "name"),
        )
        or ""
    )
    分集序号 = _安全整数(
        _嵌套取值(
            数据,
            ("page_data", "page"),
            ("pageData", "page"),
            ("page",),
            ("p",),
            ("ep", "index"),
            ("ep", "page"),
            ("episode", "index"),
            ("episode", "page"),
        ),
        1,
    )
    清晰度编号 = _安全整数(
        _嵌套取值(
            数据,
            ("video_quality",),
            ("videoQuality",),
            ("quality",),
            ("qn",),
        )
    )
    清晰度 = str(
        _嵌套取值(
            数据,
            ("quality_pithy_description",),
            ("qualityPithyDescription",),
            ("quality_description",),
            ("qualityDescription",),
        )
        or ""
    )
    清晰度上标 = str(
        _嵌套取值(
            数据,
            ("quality_superscript",),
            ("qualitySuperscript",),
        )
        or ""
    )
    if not 清晰度 and 清晰度编号:
        清晰度 = _清晰度映射.get(清晰度编号, str(清晰度编号))
    if 清晰度上标 and 清晰度上标 not in 清晰度:
        清晰度 = f"{清晰度} {清晰度上标}".strip()

    宽度 = _安全整数(
        _嵌套取值(
            数据,
            ("page_data", "width"),
            ("pageData", "width"),
            ("dimension", "width"),
            ("video", "width"),
            ("ep", "width"),
            ("episode", "width"),
        )
    )
    高度 = _安全整数(
        _嵌套取值(
            数据,
            ("page_data", "height"),
            ("pageData", "height"),
            ("dimension", "height"),
            ("video", "height"),
            ("ep", "height"),
            ("episode", "height"),
        )
    )
    字节数 = _安全整数(
        _嵌套取值(
            数据,
            ("total_bytes",),
            ("totalBytes",),
            ("total_size",),
            ("totalSize",),
            ("downloaded_bytes",),
            ("downloadedBytes",),
            ("size",),
        )
    )
    发布时间 = _格式化元数据时间(
        _嵌套取值(
            数据,
            ("pubdate",),
            ("publish_time",),
            ("publishTime",),
            ("ctime",),
            ("ep", "pub_time"),
            ("episode", "pub_time"),
        )
    )
    return {
        "标题": 标题,
        "BV号": BV号,
        "AV号": AV号,
        "UP主名称": UP主名称,
        "合集标题": 合集标题,
        "分集序号": 分集序号,
        "清晰度": 清晰度,
        "分辨率": f"{宽度}×{高度}" if 宽度 and 高度 else "",
        "字节数": 字节数,
        "发布时间": 发布时间,
    }


def _解析入口JSON(
    路径文本: 路径,
    来源标签: str,
    来源类型: str,
    序列号: str = "",
) -> 视频卡片 | None:
    r"""
    解析安卓缓存 entry.json 文件
    :param: path: entry.json 路径
    :param: source_label: 来源标签
    :param: source_type: 来源类型
    :param: serial: ADB 设备序列号
    :return: VideoCard | None
    """
    try:
        数据: dict = 数据交换.loads(路径文本.read_text(encoding="utf-8"))
    except Exception:
        return None

    父目录: 路径 = 路径文本.parent
    元数据 = _规范化入口元数据(数据, _从入口路径推断标识(路径文本))
    类型标记 = str(
        _嵌套取值(
            数据,
            ("type_tag",),
            ("typeTag",),
            ("video_quality",),
            ("videoQuality",),
            ("qn",),
        )
        or ""
    )

    视频路径: str = ""
    音频路径: str = ""

    # 优先按 type_tag（画质数字子目录）查找
    if 类型标记 and (清晰度目录 := 父目录 / 类型标记).is_dir():
        if (视频文件 := 清晰度目录 / "video.m4s").exists():
            视频路径 = str(视频文件)
        if (音频文件 := 清晰度目录 / "audio.m4s").exists():
            音频路径 = str(音频文件)

    # 降级：遍历子目录查找
    if not 视频路径:
        for 子目录 in 父目录.iterdir():
            if 子目录.is_dir():
                if (视频文件 := 子目录 / "video.m4s").exists():
                    视频路径 = str(视频文件)
                if (音频文件 := 子目录 / "audio.m4s").exists():
                    音频路径 = str(音频文件)
                if 视频路径:
                    break

    if not 视频路径:
        return None

    return 视频卡片(
        标题=元数据["标题"],
        BV号=元数据["BV号"],
        AV号=元数据["AV号"],
        UP主名称=元数据["UP主名称"],
        合集标题=元数据["合集标题"],
        分集序号=元数据["分集序号"],
        清晰度=元数据["清晰度"],
        分辨率=元数据["分辨率"],
        字节数=元数据["字节数"],
        发布时间=元数据["发布时间"],
        文件夹名=父目录.name,
        来源标签=来源标签,
        来源类型=来源类型,
        设备序列号=序列号,
        视频路径=视频路径,
        音频路径=音频路径,
        封面路径=_向上寻找封面(父目录),
        元文件路径表=_寻找本地元文件(路径(视频路径).parent),
    )


def _递归寻找M4S(根目录: 路径, 来源标签: str, 来源类型: str) -> list[视频卡片]:
    r"""
    递归搜索目录中的 video.m4s / audio.m4s 文件对（无需 JSON 元数据）
    逻辑参考 biliandout ScanWorker._find_m4s_local：
      - 当前目录同时存在两个文件 → 命中，不再递归子目录
      - 否则递归所有子目录
    :param: root: 搜索根目录
    :param: source_label: 来源标签
    :param: source_type: 来源类型
    :return: list[VideoCard]
    """
    卡片列表: list[视频卡片] = []
    视频文件: 路径 = 根目录 / "video.m4s"
    音频文件: 路径 = 根目录 / "audio.m4s"
    if 视频文件.exists() and 音频文件.exists():
        if 卡片 := _从M4S目录制卡(根目录, 来源标签, 来源类型):
            卡片列表.append(卡片)
    else:
        try:
            for 子目录 in 根目录.iterdir():
                if 子目录.is_dir():
                    卡片列表.extend(_递归寻找M4S(子目录, 来源标签, 来源类型))
        except PermissionError:
            pass
    return 卡片列表


def _解析列表输出(标准输出: str) -> list[str]:
    r"""
    解析 adb shell ls 输出，过滤空行、错误前缀、控制字符（处理彩色输出）
    参考 biliandout ScanWorker 经验：某些 Android ROM 默认 ls 输出带 ANSI 颜色
    :param: stdout: adb shell ls 原始输出
    :return: list[str]: 清理后的条目名列表
    """
    输出列表: list[str] = []
    控制码正则: 正则.Pattern[str] = 正则.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
    for 行文本 in 标准输出.splitlines():
        清理后文本: str = 控制码正则.sub("", 行文本).strip()
        if not 清理后文本:
            continue
        if 清理后文本.startswith("ls:"):
            continue
        if 清理后文本 in (".", ".."):
            continue
        输出列表.append(清理后文本)
    return 输出列表


def _寻找电脑M4S(缓存目录: 路径) -> tuple[str, str]:
    r"""
    在 PC 缓存目录中查找 video 和 audio m4s 文件（通过 codec-id 区分）
    :param: cache_dir: 缓存子目录
    :return: tuple[str, str]: (视频路径, 音频路径)
    """
    视频路径: str = ""
    音频路径: str = ""
    for 文件 in 缓存目录.iterdir():
        if 文件.suffix == ".m4s" and 文件.is_file():
            文件名片段: list[str] = 文件.stem.split("-")
            if len(文件名片段) >= 3:
                try:
                    编码编号: int = int(文件名片段[-1])
                    if 编码编号 >= _音频编码阈值:
                        音频路径 = str(文件)
                    else:
                        视频路径 = str(文件)
                except ValueError:
                    if not 视频路径:
                        视频路径 = str(文件)
            elif not 视频路径:
                视频路径 = str(文件)
    return 视频路径, 音频路径


def _解析视频信息JSON(路径文本: 路径, 来源标签: str) -> 视频卡片 | None:
    r"""
    解析 PC 缓存 videoInfo.json 文件
    :param: path: videoInfo.json 路径
    :param: source_label: 来源标签
    :return: VideoCard | None
    """
    try:
        数据: dict = 数据交换.loads(路径文本.read_text(encoding="utf-8"))
    except Exception:
        return None

    清晰度编号: int = _安全整数(数据.get("qn", 0))
    发布时间戳: int = _安全整数(数据.get("pubdate", 0))
    发布时间: str = ""
    if 发布时间戳:
        with 忽略异常(Exception):
            发布时间 = 日期时间.fromtimestamp(发布时间戳).strftime("%Y-%m-%d %H:%M")

    缓存目录: 路径 = 路径文本.parent
    视频路径, 音频路径 = _寻找电脑M4S(缓存目录)
    if not 视频路径:
        return None

    return 视频卡片(
        标题=数据.get("title", "") or 数据.get("groupTitle", ""),
        BV号=数据.get("bvid", "") or "",
        AV号=str(data_avid) if (data_avid := 数据.get("aid")) is not None else "",
        UP主名称=数据.get("uname", ""),
        合集标题=数据.get("groupTitle", "") or "",
        分集序号=_安全整数(数据.get("p", 1), 1),
        清晰度=_清晰度映射.get(清晰度编号, str(清晰度编号) if 清晰度编号 else ""),
        字节数=_安全整数(数据.get("totalSize", 0)),
        发布时间=发布时间,
        文件夹名=缓存目录.name,
        来源标签=来源标签,
        来源类型="pc",
        视频路径=视频路径,
        音频路径=音频路径,
        封面路径=_向上寻找封面(缓存目录),
        元文件路径表=_寻找本地元文件(缓存目录),
    )


def _解析索引JSON(路径文本: 路径) -> tuple[str, str, int]:
    r"""
    解析 Android 新版 index.json (与 video.m4s/audio.m4s 同目录)
    :param: path: index.json 路径
    :return: (分辨率字符串, 帧率字符串, 视频码率)
    """
    try:
        数据: dict = 数据交换.loads(路径文本.read_text(encoding="utf-8"))
    except Exception:
        return "", "", 0
    视频列表: list = 数据.get("video", []) or []
    if not 视频列表:
        return "", "", 0
    视频项: dict = 视频列表[0]
    宽度: int = _安全整数(视频项.get("width", 0))
    高度: int = _安全整数(视频项.get("height", 0))
    分辨率: str = f"{宽度}×{高度}" if 宽度 and 高度 else ""
    帧率: str = ""
    if 帧率值 := 视频项.get("frame_rate"):
        try:
            文件: float = float(帧率值)
            帧率 = f"{文件:.0f}fps" if 文件 == int(文件) else f"{文件:.1f}fps"
        except (ValueError, TypeError):
            pass
    return 分辨率, 帧率, _安全整数(视频项.get("bandwidth", 0))


def _向上寻找封面(起点: 路径, 最大深度: int = 3) -> str:
    r"""
    从 start 起向上查找 cover.jpg / cover.jpeg / cover.png (含 start 自身)
    :param: start: 起始目录
    :param: max_depth: 最多上溯层数
    :return: str: cover 路径, 找不到返回空串
    """
    当前目录: 路径 = 起点
    for _ in range(最大深度 + 1):
        for 名称 in ("cover.jpg", "cover.jpeg", "cover.png"):
            候选文件: 路径 = 当前目录 / 名称
            if 候选文件.exists():
                return str(候选文件)
        if 当前目录.parent == 当前目录:
            break
        当前目录 = 当前目录.parent
    return ""


def _寻找本地元文件(起点: 路径, 最大深度: int = 4) -> dict[str, str]:
    r"""
    从媒体目录向上寻找 Android 缓存的三类元文件，每类只取距离最近的一份。
    :param 起点: video.m4s 所在目录
    :param 最大深度: 最多上溯层数
    :return: 文件名到本地绝对路径的映射
    """
    结果: dict[str, str] = {}
    当前目录: 路径 = 起点
    for _ in range(最大深度 + 1):
        for 文件名 in _缓存元文件名:
            if 文件名 in 结果:
                continue
            候选文件: 路径 = 当前目录 / 文件名
            if 候选文件.is_file():
                结果[文件名] = str(候选文件)
        if len(结果) == len(_缓存元文件名) or 当前目录.parent == 当前目录:
            break
        当前目录 = 当前目录.parent
    return 结果


def _从M4S目录制卡(缓存媒体目录: 路径, 来源标签: str, 来源类型: str) -> 视频卡片 | None:
    r"""
    针对 "目录中含 video.m4s + audio.m4s" 的通用情况构造 VideoCard
    自动尝试解析同目录下 index.json 与上溯查找封面
    :param: m4s_dir: 包含两个 m4s 文件的目录
    :param: source_label: 来源标签
    :param: source_type: 来源类型
    :return: VideoCard | None
    """
    视频文件: 路径 = 缓存媒体目录 / "video.m4s"
    音频文件: 路径 = 缓存媒体目录 / "audio.m4s"
    if not (视频文件.exists() and 音频文件.exists()):
        return None

    大小: int = 0
    with 忽略异常(OSError):
        大小 = 视频文件.stat().st_size + 音频文件.stat().st_size

    分辨率: str = ""
    帧率: str = ""
    if (索引 := 缓存媒体目录 / "index.json").exists():
        分辨率, 帧率, _ = _解析索引JSON(索引)

    清晰度: str = ""
    with 忽略异常(ValueError):
        清晰度 = _清晰度映射.get(int(缓存媒体目录.name), "")
    if 帧率:
        清晰度 = f"{清晰度} {帧率}".strip()

    文件夹: 路径 = 缓存媒体目录.parent if 缓存媒体目录.parent != 缓存媒体目录 else 缓存媒体目录
    return 视频卡片(
        文件夹名=文件夹.name or 缓存媒体目录.name,
        来源标签=来源标签,
        来源类型=来源类型,
        视频路径=str(视频文件),
        音频路径=str(音频文件),
        字节数=大小,
        分辨率=分辨率,
        清晰度=清晰度,
        封面路径=_向上寻找封面(缓存媒体目录.parent),
        元文件路径表=_寻找本地元文件(缓存媒体目录),
    )


def _爬虫补全(卡片: 视频卡片) -> None:
    r"""
    若设置启用爬虫降级, 当卡片缺失关键元数据(title/up)时, 尝试用 BV 号补全
    :param: card: 待补全卡片 (就地修改)
    """
    超时秒数: float | None = 工具.取爬虫兜底超时()
    if 超时秒数 is None or not _有网络请求:
        return
    标题为回退值: bool = not 卡片.标题 or 卡片.标题 in {
        卡片.文件夹名,
        f"av{卡片.AV号}" if 卡片.AV号 else "",
        f"缓存视频 av{卡片.AV号}" if 卡片.AV号 else "",
    }
    if not 标题为回退值 and 卡片.UP主名称:
        return
    if not 卡片.BV号 and not 卡片.AV号:
        if 匹配 := 正则.search(r"(BV[\w]{10,})", 卡片.文件夹名 or "", 正则.IGNORECASE):
            卡片.BV号 = 匹配.group(1)
        elif (卡片.文件夹名 or "").isdigit():
            卡片.AV号 = 卡片.文件夹名
        else:
            return
    try:
        with 网络请求.Client(headers=_爬虫请求头, timeout=超时秒数) as 卡片项:
            查询参数: dict[str, str] = (
                {"bvid": 卡片.BV号} if 卡片.BV号 else {"aid": 卡片.AV号}
            )
            响应 = 卡片项.get(
                "https://api.bilibili.com/x/web-interface/view",
                params=查询参数,
            )
            数据: dict = 响应.json()
        if 数据.get("code") != 0:
            return
        信息: dict = 数据.get("data", {})
        if 标题为回退值:
            卡片.标题 = 信息.get("title", "")
        if not 卡片.BV号:
            卡片.BV号 = 信息.get("bvid", "") or ""
        if not 卡片.AV号 and 信息.get("aid") is not None:
            卡片.AV号 = str(信息.get("aid"))
        if not 卡片.UP主名称:
            卡片.UP主名称 = 信息.get("owner", {}).get("name", "")
        if not 卡片.发布时间 and (发布时间戳 := 信息.get("pubdate")):
            with 忽略异常(Exception):
                卡片.发布时间 = 日期时间.fromtimestamp(发布时间戳).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass


# ===== 扫描函数 =====


def _扫描本地目录(根目录: 路径, 来源标签: str) -> list[视频卡片]:
    r"""
    扫描本地目录：优先解析 entry.json / videoInfo.json，
    若均无则递归查找任意 video.m4s / audio.m4s 对
    :param: root: 根目录
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    卡片列表: list[视频卡片] = []
    入口文件列表: list[路径] = list(根目录.rglob("entry.json"))
    视频信息文件列表: list[路径] = list(根目录.rglob("videoInfo.json"))
    总数: int = len(入口文件列表) + len(视频信息文件列表)

    for 序号, 入口文件 in enumerate(入口文件列表):
        if 状态._扫描取消.is_set():
            break
        while 状态._扫描暂停.is_set() and not 状态._扫描取消.is_set():
            时间.sleep(0.2)
        try:
            卡片项 = _解析入口JSON(入口文件, 来源标签, "local")
            if 卡片项 and 状态.添加来源卡片(卡片项):
                卡片列表.append(卡片项)
        except Exception as e:
            状态.记录日志("warn", f"跳过损坏缓存元数据: {入口文件} — {e}")
        if 总数:
            with 状态.锁:
                状态.扫描进度 = (序号 + 1) / 总数

    for 序号, 视频信息文件 in enumerate(视频信息文件列表):
        if 状态._扫描取消.is_set():
            break
        while 状态._扫描暂停.is_set() and not 状态._扫描取消.is_set():
            时间.sleep(0.2)
        try:
            卡片项 = _解析视频信息JSON(视频信息文件, 来源标签)
            if 卡片项 and 状态.添加来源卡片(卡片项):
                卡片列表.append(卡片项)
        except Exception as e:
            状态.记录日志("warn", f"跳过损坏 PC 缓存元数据: {视频信息文件} — {e}")
        if 总数:
            with 状态.锁:
                状态.扫描进度 = (len(入口文件列表) + 序号 + 1) / 总数

    # 通用回退：当目录中没有任何 JSON 元数据时，递归查找 m4s 对
    if not 卡片列表 and not 入口文件列表 and not 视频信息文件列表:
        回退卡片列表: list[视频卡片] = _递归寻找M4S(根目录, 来源标签, "local")
        for 卡片项 in 回退卡片列表:
            if 状态.添加来源卡片(卡片项):
                卡片列表.append(卡片项)

    return 卡片列表


def _扫描电脑缓存(根目录: 路径, 来源标签: str) -> list[视频卡片]:
    r"""
    扫描 PC 桌面端缓存目录
    :param: root: 缓存根目录
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    卡片列表: list[视频卡片] = []
    if not 根目录.is_dir():
        状态.记录日志("error", f"PC 缓存路径不存在: {根目录}")
        return 卡片列表

    子目录列表: list[路径] = [子目录项 for 子目录项 in 根目录.iterdir() if 子目录项.is_dir()]
    总数: int = len(子目录列表)

    for 序号, 子目录路径 in enumerate(子目录列表):
        if 状态._扫描取消.is_set():
            break
        while 状态._扫描暂停.is_set() and not 状态._扫描取消.is_set():
            时间.sleep(0.2)

        try:
            if (视频信息文件 := 子目录路径 / "videoInfo.json").exists():
                if (卡片项 := _解析视频信息JSON(视频信息文件, 来源标签)) and 状态.添加来源卡片(卡片项):
                    卡片列表.append(卡片项)
            else:
                视频路径, 音频路径 = _寻找电脑M4S(子目录路径)
                if 视频路径:
                    卡片项 = 视频卡片(
                        文件夹名=子目录路径.name,
                        来源标签=来源标签,
                        来源类型="pc",
                        视频路径=视频路径,
                        音频路径=音频路径,
                        封面路径=_向上寻找封面(路径(视频路径).parent),
                    )
                    if 状态.添加来源卡片(卡片项):
                        卡片列表.append(卡片项)
                else:
                    for 嵌套卡片 in _递归寻找M4S(子目录路径, 来源标签, "pc"):
                        if 状态.添加来源卡片(嵌套卡片):
                            卡片列表.append(嵌套卡片)
        except Exception as e:
            状态.记录日志("warn", f"跳过损坏 PC 缓存目录: {子目录路径} — {e}")

        if 总数:
            with 状态.锁:
                状态.扫描进度 = (序号 + 1) / 总数

    return 卡片列表


def _扫描磁盘(根目录: 路径, 来源标签: str) -> list[视频卡片]:
    r"""
    扫描挂载为本地驱动器的 Android 设备缓存
    :param: root: 下载目录（如 E:/Android/data/tv.danmaku.bili/download）
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    卡片列表: list[视频卡片] = []
    if not 根目录.is_dir():
        状态.记录日志("error", f"驱动器缓存路径不存在: {根目录}")
        return 卡片列表

    入口文件列表: list[路径] = list(根目录.rglob("entry.json"))
    总数: int = len(入口文件列表)

    for 序号, 入口文件 in enumerate(入口文件列表):
        if 状态._扫描取消.is_set():
            break
        while 状态._扫描暂停.is_set() and not 状态._扫描取消.is_set():
            时间.sleep(0.2)
        try:
            卡片项 = _解析入口JSON(入口文件, 来源标签, "drive")
            if 卡片项 and 状态.添加来源卡片(卡片项):
                卡片列表.append(卡片项)
        except Exception as e:
            状态.记录日志("warn", f"跳过损坏挂载盘缓存元数据: {入口文件} — {e}")
        if 总数:
            with 状态.锁:
                状态.扫描进度 = (序号 + 1) / 总数

    # 通用回退
    if not 卡片列表 and not 入口文件列表:
        回退卡片列表: list[视频卡片] = _递归寻找M4S(根目录, 来源标签, "drive")
        for 卡片项 in 回退卡片列表:
            if 状态.添加来源卡片(卡片项):
                卡片列表.append(卡片项)

    return 卡片列表


def _列出ADB文件(ADB路径: str, 序列号: str, 远端根目录: str) -> set[str]:
    r"""一次 ``find`` 获取整个缓存树，避免逐目录、逐普通文件执行 ``ls``。"""
    执行结果: 子进程.CompletedProcess = _执行ADB(
        ADB路径,
        序列号,
        "shell",
        f"find {命令行转义.quote(远端根目录)} -type f",
        超时秒数=60,
    )
    if 执行结果.returncode != 0:
        错误文本 = (执行结果.stderr or 执行结果.stdout or "未知 ADB 错误").strip()
        raise RuntimeError(错误文本[:300])
    return {
        行.strip()
        for 行 in 执行结果.stdout.splitlines()
        if 行.strip().startswith("/") and not 行.strip().startswith("find:")
    }


def _取ADB媒体目录列表(远端文件集合: set[str]) -> list[str]:
    目录文件名表: dict[str, set[str]] = {}
    for 文件路径 in 远端文件集合:
        if "/" not in 文件路径:
            continue
        目录文本, 文件名 = 文件路径.rsplit("/", 1)
        if 文件名 in {"video.m4s", "audio.m4s"}:
            目录文件名表.setdefault(目录文本, set()).add(文件名)
    return sorted(
        目录文本
        for 目录文本, 文件名集合 in 目录文件名表.items()
        if {"video.m4s", "audio.m4s"} <= 文件名集合
    )


def _扫描ADB文件夹(
    ADB路径: str,
    序列号: str,
    远端路径: str,
    根文件夹: str,
    来源标签: str,
) -> list[视频卡片]:
    r"""
    以单次 ``find`` 搜索 ADB 目录中的 video.m4s / audio.m4s 文件对。
    :param: adb: adb 路径
    :param: serial: 设备序列号
    :param: remote_path: 当前远端目录
    :param: root_folder: 根文件夹名（用于标题回退）
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    卡片列表: list[视频卡片] = []
    try:
        远端文件集合 = _列出ADB文件(ADB路径, 序列号, 远端路径)
        媒体目录列表 = _取ADB媒体目录列表(远端文件集合)
        for 媒体目录 in 媒体目录列表:
            if 状态._扫描取消.is_set():
                break
            while 状态._扫描暂停.is_set() and not 状态._扫描取消.is_set():
                时间.sleep(0.2)
            if 卡片 := _制作ADB卡片(
                ADB路径,
                序列号,
                媒体目录,
                根文件夹,
                来源标签,
                远端文件集合,
            ):
                卡片列表.append(卡片)
    except Exception as e:
        状态.记录日志("warn", f"扫描 ADB 目录失败: {远端路径} — {e}")
    return 卡片列表


def _遍历ADB包(包名: str) -> list[tuple[str, str]]:
    请求包名: str = 包名.strip()
    if not 请求包名:
        return list(_哔哩包列表)
    if 请求包名 in _哔哩包名表:
        return [(请求包名, _哔哩包名表[请求包名])]
    状态.记录日志("warn", f"未知 B 站包名: {请求包名}")
    return []


def _取ADB下载目录候选(包名: str) -> list[str]:
    r"""兼容普通版、概念版及国际版使用过的两种外置存储布局。"""
    应用目录 = f"/sdcard/Android/data/{包名}"
    return [f"{应用目录}/download", f"{应用目录}/files/download"]


def _拉取ADB封面(
    ADB路径: str,
    序列号: str,
    远端目录: str,
    标识符: str,
    远端文件集合: set[str] | None = None,
) -> str:
    r"""
    从 ADB 设备拉取 cover.jpg 到本地缓存目录，命中缓存直接返回
    参考 biliandout ScanWorker._pull_cover_adb
    :param: adb: adb 路径
    :param: serial: 设备序列号
    :param: remote_dir: 远端目录（向上搜索起点）
    :param: identifier: 唯一标识（用于哈希命名）
    :return: str: 本地缓存路径, 失败返回空串
    """
    安全编号: str = 哈希.md5(
        f"{序列号}_{远端目录}_{标识符}".encode()
    ).hexdigest()
    for 扩展名 in ("jpg", "jpeg", "png"):
        缓存文件: 路径 = _封面缓存目录 / f"{安全编号}.{扩展名}"
        if 缓存文件.exists() and 缓存文件.stat().st_size > 0:
            return str(缓存文件)

    当前目录: str = 远端目录
    for _ in range(4):
        for 扩展名 in ("jpg", "jpeg", "png"):
            目标文件: 路径 = _封面缓存目录 / f"{安全编号}.{扩展名}"
            远端封面路径 = f"{当前目录}/cover.{扩展名}"
            if 远端文件集合 is not None and 远端封面路径 not in 远端文件集合:
                continue
            try:
                执行结果: 子进程.CompletedProcess = _执行ADB(
                    ADB路径,
                    序列号,
                    "pull",
                    远端封面路径,
                    str(目标文件),
                    超时秒数=15,
                )
                if 执行结果.returncode == 0 and 目标文件.exists() and 目标文件.stat().st_size > 0:
                    return str(目标文件)
            except Exception:
                pass
            目标文件.unlink(missing_ok=True)
        if "/" not in 当前目录:
            break
        当前目录 = 当前目录.rsplit("/", 1)[0]
    return ""


def _取ADB元数据目录候选(远端路径: str) -> list[str]:
    r"""返回 m4s 目录向上的元数据目录候选，优先 ``c_<cid>`` 层。"""
    当前目录: str = 远端路径.rstrip("/").rsplit("/", 1)[0]
    候选目录: list[str] = []
    while 当前目录 and 当前目录 not in 候选目录:
        候选目录.append(当前目录)
        if 当前目录.rstrip("/").endswith("/download") or "/download/" not in 当前目录:
            break
        上级目录: str = 当前目录.rsplit("/", 1)[0]
        if 上级目录 == 当前目录:
            break
        当前目录 = 上级目录
    return 候选目录


def _寻找ADB元文件(远端媒体目录: str, 远端文件集合: set[str] | None) -> dict[str, str]:
    r"""
    根据一次 find 得到的远端文件集合，定位最靠近媒体目录的缓存元文件。
    未提供文件集合时不猜测不存在的远端文件，避免导出阶段产生多次失败拉取。
    """
    if 远端文件集合 is None:
        return {}
    候选目录: list[str] = [远端媒体目录.rstrip("/")]
    候选目录.extend(_取ADB元数据目录候选(远端媒体目录))
    结果: dict[str, str] = {}
    for 目录 in 候选目录:
        for 文件名 in _缓存元文件名:
            if 文件名 in 结果:
                continue
            候选路径: str = f"{目录}/{文件名}"
            if 候选路径 in 远端文件集合:
                结果[文件名] = 候选路径
    return 结果


def _制作ADB卡片(
    ADB路径: str,
    序列号: str,
    远端路径: str,
    根文件夹: str,
    来源标签: str,
    远端文件集合: set[str] | None = None,
) -> 视频卡片 | None:
    r"""
    解析 ADB 设备上某 m4s 目录，尝试拉取 entry.json / index.json 获取元数据后生成 VideoCard
    参考 biliandout ScanWorker._parse_video_adb
    :param: adb: adb 路径
    :param: serial: 设备序列号
    :param: remote_path: 包含 video.m4s/audio.m4s 的远端目录
    :param: root_folder: 根文件夹名
    :param: source_label: 来源标签
    :return: VideoCard | None
    """
    标题: str = 根文件夹
    清晰度: str = ""
    分辨率: str = ""
    帧率: str = ""
    字节数: int = 0
    BV号: str = ""
    AV号: str = 根文件夹 if 根文件夹.isdigit() else ""
    UP主名称: str = ""
    合集标题: str = ""
    分集序号: int = 1
    发布时间: str = ""
    元文件路径表: dict[str, str] = _寻找ADB元文件(远端路径, 远端文件集合)

    # Android 普通版常将 entry.json / cover.jpg 放在 c_<cid> 层，
    # 其他版本则可能放在 AV 目录；从 m4s 所在目录逐层向上探测。
    远端父目录: str = _取ADB元数据目录候选(远端路径)[0]
    for 元数据目录 in _取ADB元数据目录候选(远端路径):
        远端入口路径 = f"{元数据目录}/entry.json"
        if 远端文件集合 is not None and 远端入口路径 not in 远端文件集合:
            continue
        临时路径: str = ""
        try:
            with 临时文件.NamedTemporaryFile(suffix=".json", delete=False) as 临时对象:
                临时路径 = 临时对象.name
            拉取结果: 子进程.CompletedProcess = _执行ADB(
                ADB路径,
                序列号,
                "pull",
                远端入口路径,
                临时路径,
                超时秒数=10,
            )
            if 拉取结果.returncode != 0 or not 路径(临时路径).exists():
                continue
            数据: dict = 数据交换.loads(路径(临时路径).read_text(encoding="utf-8"))
            元数据 = _规范化入口元数据(数据, AV号 or 根文件夹)
            标题 = 元数据["标题"] or 根文件夹
            BV号 = 元数据["BV号"]
            AV号 = 元数据["AV号"] or AV号
            UP主名称 = 元数据["UP主名称"]
            合集标题 = 元数据["合集标题"]
            分集序号 = 元数据["分集序号"]
            清晰度 = 元数据["清晰度"]
            分辨率 = 元数据["分辨率"]
            字节数 = 元数据["字节数"]
            发布时间 = 元数据["发布时间"]
            远端父目录 = 元数据目录
            元文件路径表["entry.json"] = 远端入口路径
            break
        except Exception:
            continue
        finally:
            if 临时路径:
                路径(临时路径).unlink(missing_ok=True)

    # 尝试拉取 index.json 解析分辨率/帧率（与 m4s 同目录）
    远端索引路径 = f"{远端路径}/index.json"
    if (
        (not 分辨率 or not 帧率)
        and (远端文件集合 is None or 远端索引路径 in 远端文件集合)
    ):
        索引临时路径: str = ""
        try:
            with 临时文件.NamedTemporaryFile(suffix=".json", delete=False) as 临时对象:
                索引临时路径 = 临时对象.name
            索引拉取结果: 子进程.CompletedProcess = _执行ADB(
                ADB路径,
                序列号,
                "pull",
                远端索引路径,
                索引临时路径,
                超时秒数=10,
            )
            if 索引拉取结果.returncode == 0 and 路径(索引临时路径).exists():
                解析分辨率, 解析帧率, _ = _解析索引JSON(路径(索引临时路径))
                if not 分辨率 and 解析分辨率:
                    分辨率 = 解析分辨率
                if 解析帧率:
                    帧率 = 解析帧率
        except Exception:
            pass
        finally:
            if 索引临时路径:
                路径(索引临时路径).unlink(missing_ok=True)

    # 从目录名推断画质
    if not 清晰度:
        with 忽略异常(ValueError, IndexError):
            清晰度 = _清晰度映射.get(int(远端路径.rsplit("/", 1)[-1]), "")
    if 帧率:
        清晰度 = f"{清晰度} {帧率}".strip()

    if 标题 == 根文件夹 and AV号:
        标题 = f"缓存视频 av{AV号}"

    # 拉取封面（向上 4 层查找）
    封面路径: str = _拉取ADB封面(
        ADB路径,
        序列号,
        远端父目录,
        根文件夹,
        远端文件集合,
    )

    # 若 entry.json 未提供大小，通过 stat 获取
    if not 字节数:
        try:
            统计结果: 子进程.CompletedProcess = _执行ADB(
                ADB路径,
                序列号,
                "shell",
                f"stat -c %s '{远端路径}/video.m4s' '{远端路径}/audio.m4s'",
                超时秒数=10,
            )
            if 统计结果.returncode == 0:
                字节数 = sum(int(行文本.strip()) for 行文本 in 统计结果.stdout.splitlines() if 行文本.strip().isdigit())
        except Exception:
            pass

    return 视频卡片(
        标题=标题,
        BV号=BV号,
        AV号=AV号,
        UP主名称=UP主名称,
        合集标题=合集标题,
        分集序号=分集序号,
        清晰度=清晰度,
        分辨率=分辨率,
        字节数=字节数,
        发布时间=发布时间,
        文件夹名=根文件夹,
        来源标签=来源标签,
        来源类型="adb",
        设备序列号=序列号,
        视频路径=f"{远端路径}/video.m4s",
        音频路径=f"{远端路径}/audio.m4s",
        封面路径=封面路径,
        元文件路径表=元文件路径表,
    )


def _扫描ADB设备(序列号: str, 来源标签: str, 包名: str = "") -> list[视频卡片]:
    r"""
    扫描 ADB 设备上所有哔哩哔哩包的下载目录
    参考 biliandout ScanWorker._scan_adb
    :param: serial: 设备序列号
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    卡片列表: list[视频卡片] = []
    ADB路径: str | None = _寻找ADB()
    if not ADB路径:
        状态.记录日志("error", "未找到 ADB 可执行文件，请安装 ADB 并将其加入 PATH")
        return 卡片列表
    在线序列号集合 = {设备序列号 for 设备序列号, _ in _取ADB设备列表()}
    if 序列号 not in 在线序列号集合:
        raise RuntimeError(f"ADB 设备已离线或未授权: {序列号}")

    for 包名项, 包显示名 in _遍历ADB包(包名):
        扫描项目列表: list[tuple[str, str, set[str]]] = []
        目录可访问 = False
        for 远端根目录 in _取ADB下载目录候选(包名项):
            try:
                远端文件集合 = _列出ADB文件(ADB路径, 序列号, 远端根目录)
                目录可访问 = True
                扫描项目列表.extend(
                    (媒体目录, 远端根目录, 远端文件集合)
                    for 媒体目录 in _取ADB媒体目录列表(远端文件集合)
                )
            except Exception as e:
                错误文本 = str(e)
                小写错误 = 错误文本.lower()
                if "no such file or directory" in 小写错误:
                    continue
                if "device" in 小写错误 and (
                    "not found" in 小写错误
                    or "offline" in 小写错误
                    or "unauthorized" in 小写错误
                ):
                    raise RuntimeError(f"ADB 设备连接中断: {序列号}") from e
                状态.记录日志("warn", f"扫描 {包显示名} 目录失败: {远端根目录} — {e}")

        if not 扫描项目列表:
            if 目录可访问 or not 状态._扫描取消.is_set():
                状态.记录日志("info", f"{包显示名}暂无本地缓存")
            continue

        总数 = len(扫描项目列表)

        def _制作目录卡片(扫描项目: tuple[str, str, set[str]]) -> 视频卡片 | None:
            媒体目录, 远端根目录, 远端文件集合 = 扫描项目
            if 状态._扫描取消.is_set():
                return None
            while 状态._扫描暂停.is_set() and not 状态._扫描取消.is_set():
                时间.sleep(0.2)
            相对路径 = 媒体目录.removeprefix(f"{远端根目录}/")
            根文件夹 = (
                相对路径.split("/", 1)[0]
                if 相对路径
                else 媒体目录.rsplit("/", 1)[-1]
            )
            return _制作ADB卡片(
                ADB路径,
                序列号,
                媒体目录,
                根文件夹,
                来源标签,
                远端文件集合,
            )

        with 线程池执行器(max_workers=min(4, 总数)) as 扫描池:
            扫描任务表 = {
                扫描池.submit(_制作目录卡片, 扫描项目): 扫描项目[0]
                for 扫描项目 in 扫描项目列表
            }
            for 完成序号, 扫描任务 in enumerate(逐个完成(扫描任务表), start=1):
                try:
                    卡片项 = 扫描任务.result()
                    if 卡片项 and 状态.添加来源卡片(卡片项):
                        卡片列表.append(卡片项)
                except Exception as e:
                    状态.记录日志(
                        "warn",
                        f"跳过损坏 ADB 缓存: {扫描任务表[扫描任务]} — {e}",
                    )
                with 状态.锁:
                    状态.扫描进度 = 完成序号 / 总数

    return 卡片列表


def _扫描线程函数(
    来源类型: str,
    路径文本: str,
    标签: str,
    序列号: str,
    包名: str,
) -> None:
    r"""
    扫描线程入口函数
    :param: source_type: 来源类型（pc / drive / adb / local）
    :param: path: 扫描路径（adb 时为空）
    :param: label: 来源标签
    :param: serial: ADB 设备序列号
    :param: package: 保留参数
    """
    发现列表: list[视频卡片] = []
    已取消: bool = False
    try:
        状态.记录日志("info", f"开始扫描: {标签}")

        match 来源类型:
            case "pc":
                发现列表 = _扫描电脑缓存(路径(路径文本), 标签)
            case "drive":
                发现列表 = _扫描磁盘(路径(路径文本), 标签)
            case "adb":
                发现列表 = _扫描ADB设备(序列号, 标签, 包名)
            case _:
                发现列表 = _扫描本地目录(路径(路径文本), 标签)

        if 工具.取爬虫兜底超时() is not None and not 状态._扫描取消.is_set():
            for 卡片项 in 发现列表:
                if 状态._扫描取消.is_set():
                    break
                if not (卡片项.标题 and 卡片项.UP主名称):
                    _爬虫补全(卡片项)

        已取消 = 状态._扫描取消.is_set()
        if 已取消:
            状态.记录日志("warn", "扫描已取消")
        else:
            状态.记录日志("success", f"扫描完成: 发现 {len(发现列表)} 个视频")
    except Exception as e:
        状态.记录日志("error", f"扫描异常: {e}")
    finally:
        已取消 = 已取消 or 状态._扫描取消.is_set()
        with 状态.锁:
            状态.扫描状态 = "idle"
            if not 已取消:
                状态.扫描进度 = 1.0
            状态._扫描取消.clear()
            状态._扫描暂停.clear()


# ===== 导出函数 =====


def _构建文件名(卡片: 视频卡片) -> str:
    r"""
    按设置中的 name_parts 组合导出文件名
    :param: card: 视频卡片
    :return: str: 文件名（含 .mp4），空串表示应跳过
    """
    原始配置: str = 工具.取设置("localout", "name_parts")
    片段集合: set[str] = set(原始配置.split(","))
    处理策略: str = 工具.取设置("localout", "incomplete_title_action")

    显示标题: str = 卡片.标题
    if not 显示标题:
        if 处理策略 == "skip":
            return ""
        显示标题 = 卡片.文件夹名 or "untitled"

    主片段列表: list[str] = []
    if "up" in 片段集合 and 卡片.UP主名称:
        主片段列表.append(卡片.UP主名称)

    中段: str = ""
    if "bv" in 片段集合 and (稿件号 := 卡片.BV号 or (f"av{卡片.AV号}" if 卡片.AV号 else "")):
        中段 += f"{{{稿件号}}}"
    分组段: str = ""
    if "group" in 片段集合 and 卡片.合集标题:
        分组段 += 卡片.合集标题
    if "part" in 片段集合:
        分组段 += f"[P{卡片.分集序号}]"
    if 分组段:
        中段 += f"({分组段})"
    if 中段:
        主片段列表.append(中段)

    if "title" in 片段集合:
        主片段列表.append(显示标题)

    主文件名: str = "--".join(主片段列表) if 主片段列表 else "untitled"
    尾部片段: list[str] = []
    if "publish_time" in 片段集合 and 卡片.发布时间:
        尾部片段.append(卡片.发布时间)
    if "export_time" in 片段集合:
        尾部片段.append(f"导出于{_完整时间()}")
    if 尾部片段:
        主文件名 += "--" + ",".join(尾部片段)

    return _清理文件名(主文件名) + ".mp4"


def _取PC缓存前缀长度(文件路径: str) -> int:
    r"""识别桌面端缓存写在 MP4 ``ftyp`` 盒之前的九字节占位头。"""
    try:
        with open(文件路径, "rb") as 输入流:
            文件头 = 输入流.read(17)
    except OSError:
        return 0
    if 文件头.startswith(b"000000000") and 文件头[13:17] == b"ftyp":
        return 9
    return 0


def _复制并移除前缀(源文件: str, 目标文件: 路径, 前缀长度: int) -> None:
    with open(源文件, "rb") as 输入流, open(目标文件, "wb") as 输出流:
        输入流.seek(前缀长度)
        文件工具.copyfileobj(输入流, 输出流, length=8 * 1024 * 1024)


def _用随包FFmpeg合并(视频文件: str, 音频文件: str, 输出路径: str) -> None:
    r"""兼容桌面端占位头，以临时文件无损封装并原子替换最终 MP4。"""
    转码器: str | None = _寻找FFmpeg()
    if not 转码器:
        raise RuntimeError("未找到 ffmpeg（请确认绿色包 bin/ 完整）")
    最终输出: 路径 = 路径(输出路径)
    最终输出.parent.mkdir(parents=True, exist_ok=True)
    临时输出: 路径 = 最终输出.parent / (
        f".{最终输出.stem}.{唯一编号.uuid4().hex}.part{最终输出.suffix or '.mp4'}"
    )

    with 临时文件.TemporaryDirectory(prefix="mybiout_pc_m4s_") as 兼容目录文本:
        兼容目录: 路径 = 路径(兼容目录文本)
        实际输入列表: list[str] = []
        for 序号, 原始文件 in enumerate((视频文件, 音频文件)):
            前缀长度: int = _取PC缓存前缀长度(原始文件)
            if 前缀长度:
                兼容文件: 路径 = 兼容目录 / f"{序号}.m4s"
                _复制并移除前缀(原始文件, 兼容文件, 前缀长度)
                实际输入列表.append(str(兼容文件))
            else:
                实际输入列表.append(原始文件)

        命令: list[str] = [
            转码器,
            "-y",
            "-i",
            实际输入列表[0],
            "-i",
            实际输入列表[1],
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(临时输出),
        ]
        try:
            结果: 子进程.CompletedProcess = 子进程.run(
                命令,
                stdin=子进程.DEVNULL,
                stdout=子进程.PIPE,
                stderr=子进程.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                **_子进程附加参数,
            )
            if (
                结果.returncode != 0
                or not 临时输出.is_file()
                or 临时输出.stat().st_size == 0
            ):
                错误文本: str = (
                    getattr(结果, "stderr", "")
                    or getattr(结果, "stdout", "")
                    or "未知 ffmpeg 错误"
                ).strip()
                raise RuntimeError(f"ffmpeg 合并失败: {错误文本[-500:]}")
            系统.replace(临时输出, 最终输出)
        finally:
            临时输出.unlink(missing_ok=True)


def _输出路径键(文件路径: 路径) -> str:
    return 系统.path.normcase(系统.path.abspath(str(文件路径)))


def _导出身份键(卡片: 视频卡片) -> str:
    r"""生成导出身份；有稿件号时跨来源判重，无稿件号时宁可多导也不误判。"""
    分集: int = max(1, _安全整数(卡片.分集序号, 1))
    清晰度指纹原文: str = "|".join(
        _安全文本(值).casefold()
        for 值 in (卡片.清晰度, 卡片.分辨率)
        if _安全文本(值)
    )
    if 清晰度指纹原文:
        版本指纹: str = f":q{哈希.sha256(清晰度指纹原文.encode('utf-8')).hexdigest()[:12]}"
    elif 卡片.字节数 > 0:
        版本指纹 = f":s{卡片.字节数}"
    else:
        版本指纹 = ""
    if 卡片.BV号:
        return f"bvid:{_安全文本(卡片.BV号).lower()}:p{分集}{版本指纹}"
    if 卡片.AV号:
        return f"avid:{_安全文本(卡片.AV号).lower().removeprefix('av')}:p{分集}{版本指纹}"
    归一文本: str = "|".join(
        正则.sub(r"\s+", " ", 值 or "").strip().casefold()
        for 值 in (卡片.标题, 卡片.UP主名称, 卡片.合集标题, 卡片.文件夹名)
    )
    # 标题、体积等弱信息可能完全相同，不能据此把两条不同视频当作重复。
    # 缓存拿不到 avid / bvid 时把来源坐标纳入哈希；代价只是跨设备不判重，
    # 好过静默跳过用户真正想导出的同名内容。
    来源坐标: str = "|".join(
        _安全文本(值).casefold()
        for 值 in (
            卡片.来源类型,
            卡片.设备序列号,
            卡片.视频路径,
            卡片.音频路径,
        )
    )
    原文: str = (
        f"{归一文本}|p{分集}|size:{max(0, 卡片.字节数)}|source:{来源坐标}"
    )
    return f"fallback:{哈希.sha256(原文.encode('utf-8')).hexdigest()[:32]}"


def _取导出身份锁(身份键: str) -> 线程.Lock:
    r"""同一批并发任务中的相同视频串行处理，避免重复写出两份。"""
    with _导出身份锁表锁:
        if 身份键 not in _导出身份锁表:
            _导出身份锁表[身份键] = 线程.Lock()
        return _导出身份锁表[身份键]


def _导出索引路径(输出目录: 路径) -> 路径:
    return 输出目录 / _导出索引文件名


def _载入导出索引(输出目录: 路径) -> dict:
    r"""读取 LocalOut 隐藏索引；损坏或旧格式时安全回退为空索引。"""
    索引文件: 路径 = _导出索引路径(输出目录)
    try:
        数据: object = 数据交换.loads(索引文件.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"version": 1, "items": {}}
    if not isinstance(数据, dict) or not isinstance(数据.get("items"), dict):
        return {"version": 1, "items": {}}
    return 数据


def _索引文件转绝对路径(输出目录: 路径, 相对路径文本: object) -> 路径 | None:
    r"""将索引中的相对路径限制在输出目录内，拒绝损坏索引造成的路径穿越。"""
    if not isinstance(相对路径文本, str) or not 相对路径文本.strip():
        return None
    try:
        根目录: 路径 = 输出目录.resolve()
        候选文件: 路径 = (输出目录 / 相对路径文本).resolve()
    except (OSError, RuntimeError):
        return None
    if 候选文件 == 根目录 or 根目录 not in 候选文件.parents:
        return None
    return 候选文件


def _从索引查找重复(
    输出目录: 路径,
    身份键: str,
    卡片: 视频卡片,
    *,
    需要元文件: bool,
) -> 路径 | None:
    with _导出索引锁:
        索引: dict = _载入导出索引(输出目录)
        项: object = 索引.get("items", {}).get(身份键)
    if not isinstance(项, dict):
        return None
    if 需要元文件 and not bool(项.get("preserved_metadata")):
        return None
    if 需要元文件:
        # 后来遇到元文件更完整的同一稿件时，不应被早期的不完整归档拦住。
        当前可保留: set[str] = set(卡片.元文件路径表).intersection(_缓存元文件名)
        已保留: set[str] = {
            str(文件名)
            for 文件名 in (项.get("metadata_files") or [])
            if str(文件名) in _缓存元文件名
        }
        if 当前可保留 and not 当前可保留.issubset(已保留):
            return None
    旧大小: int = _安全整数(项.get("source_size"))
    新大小: int = max(0, 卡片.字节数)
    if 旧大小 and 新大小:
        大小容差: int = max(1024 * 1024, int(max(旧大小, 新大小) * 0.02))
        if abs(旧大小 - 新大小) > 大小容差:
            return None
    旧清晰度: str = str(项.get("quality") or "").strip().casefold()
    新清晰度: str = (卡片.清晰度 or "").strip().casefold()
    if 旧清晰度 and 新清晰度 and 旧清晰度 != 新清晰度:
        return None
    旧分辨率: str = str(项.get("resolution") or "").strip().casefold()
    新分辨率: str = (卡片.分辨率 or "").strip().casefold()
    if 旧分辨率 and 新分辨率 and 旧分辨率 != 新分辨率:
        return None
    已有文件: 路径 | None = _索引文件转绝对路径(输出目录, 项.get("path"))
    if 已有文件 is not None and 已有文件.is_file() and 已有文件.stat().st_size > 0:
        return 已有文件
    return None


def _保存导出索引项(
    输出目录: 路径,
    身份键: str,
    输出文件: 路径,
    卡片: 视频卡片,
    *,
    已保留元文件: bool,
    元文件名称列表: list[str] | None = None,
    元文件时间戳已保留: bool = True,
    导出警告列表: list[str] | None = None,
) -> None:
    r"""以临时文件原子更新导出索引，不把机器绝对路径写入索引。"""
    with _导出索引锁:
        索引: dict = _载入导出索引(输出目录)
        项们: dict = 索引.setdefault("items", {})
        try:
            相对路径: str = 输出文件.resolve().relative_to(输出目录.resolve()).as_posix()
        except (OSError, ValueError):
            return
        项们[身份键] = {
            "path": 相对路径,
            "bvid": 卡片.BV号,
            "avid": 卡片.AV号,
            "part": max(1, _安全整数(卡片.分集序号, 1)),
            "source_size": max(0, 卡片.字节数),
            "quality": 卡片.清晰度,
            "resolution": 卡片.分辨率,
            "preserved_metadata": 已保留元文件,
            "metadata_files": sorted(set(元文件名称列表 or [])),
            "metadata_timestamps_preserved": 元文件时间戳已保留,
            "warnings": list(导出警告列表 or []),
            "exported_at": _完整时间(),
        }
        索引["version"] = 1
        临时索引: 路径 = _导出索引路径(输出目录).with_name(
            f"{_导出索引文件名}.{唯一编号.uuid4().hex}.tmp"
        )
        try:
            临时索引.write_text(
                数据交换.dumps(索引, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            系统.replace(临时索引, _导出索引路径(输出目录))
        finally:
            临时索引.unlink(missing_ok=True)


def _大小近似(文件: 路径, 预期字节数: int) -> bool:
    if 预期字节数 <= 0:
        return False
    try:
        实际字节数: int = 文件.stat().st_size
    except OSError:
        return False
    容差: int = max(2 * 1024 * 1024, int(预期字节数 * 0.03))
    return abs(实际字节数 - 预期字节数) <= 容差


def _查找旧版同名导出(
    输出目录: 路径,
    文件名文本: str,
    卡片: 视频卡片,
    *,
    保留元文件: bool,
) -> 路径 | None:
    r"""兼容索引功能上线前的导出：仅在文件体积吻合或文件名含稿件号时判重。"""
    文件名路径: 路径 = 路径(文件名文本)
    if 保留元文件:
        候选: 路径 = 输出目录 / 文件名路径.stem / 文件名路径.name
    else:
        候选 = 输出目录 / 文件名路径.name
    if not 候选.is_file() or 候选.stat().st_size <= 0:
        return None
    标识: str = (卡片.BV号 or (f"av{卡片.AV号}" if 卡片.AV号 else "")).casefold()
    if _大小近似(候选, 卡片.字节数) or (标识 and 标识 in 候选.name.casefold()):
        return 候选
    return None


def _预留输出路径(输出目录: 路径, 文件名文本: str) -> 路径:
    基础路径: 路径 = 输出目录 / 文件名文本
    with 状态.锁:
        计数器: int = 0
        while True:
            候选路径: 路径 = (
                基础路径
                if 计数器 == 0
                else 输出目录 / f"{基础路径.stem}_{计数器}{基础路径.suffix}"
            )
            路径键: str = _输出路径键(候选路径)
            if not 候选路径.exists() and 路径键 not in 状态._输出占用集合:
                状态._输出占用集合.add(路径键)
                return 候选路径
            计数器 += 1


def _预留归档目录(输出目录: 路径, 文件名文本: str) -> tuple[路径, 路径]:
    r"""预留与 MP4 同名的归档目录，返回（目录，目录内 MP4）。"""
    基础名称: str = 路径(文件名文本).stem
    with 状态.锁:
        计数器: int = 0
        while True:
            目录名称: str = 基础名称 if 计数器 == 0 else f"{基础名称}_{计数器}"
            候选目录: 路径 = 输出目录 / 目录名称
            路径键: str = _输出路径键(候选目录)
            if not 候选目录.exists() and 路径键 not in 状态._输出占用集合:
                状态._输出占用集合.add(路径键)
                return 候选目录, 候选目录 / f"{目录名称}.mp4"
            计数器 += 1


def _释放输出路径(文件路径: 路径) -> None:
    with 状态.锁:
        状态._输出占用集合.discard(_输出路径键(文件路径))


def _记录元文件时间戳警告(
    目标目录: 路径,
    文件名: str,
    源路径: str,
    首次错误: str,
) -> str:
    r"""把 ADB 降级警告同时写入界面、输出日志和归档标记。"""
    简短错误 = " ".join(首次错误.replace("\r", " ").replace("\n", " ").split())[:240]
    警告 = (
        f"{文件名} 的 adb pull -a 失败，将使用普通 adb pull 容错；"
        f"归档“{目标目录.name}”的该文件时间戳可能未保留"
    )
    状态.记录日志("warn", 警告)

    记录 = {
        "recorded_at": _完整时间(),
        "archive": 目标目录.name,
        "file": 文件名,
        "source": 源路径,
        "timestamp_preserved": False,
        "warning": 警告,
        "adb_pull_a_error": 简短错误,
    }
    标记文件 = 目标目录 / _归档元数据文件名
    日志文件 = 目标目录.parent / _导出警告日志文件名

    with _导出警告日志锁:
        标记数据: dict = {"version": 1, "metadata_timestamps_preserved": False, "warnings": []}
        if 标记文件.is_file():
            try:
                已有数据 = 数据交换.loads(标记文件.read_text(encoding="utf-8"))
                if isinstance(已有数据, dict):
                    标记数据.update(已有数据)
            except (OSError, ValueError, TypeError):
                pass
        警告记录 = 标记数据.setdefault("warnings", [])
        if not isinstance(警告记录, list):
            警告记录 = []
            标记数据["warnings"] = 警告记录
        警告记录.append(记录)
        标记数据["metadata_timestamps_preserved"] = False
        临时标记 = 标记文件.with_name(f"{标记文件.name}.{唯一编号.uuid4().hex}.tmp")
        try:
            临时标记.write_text(
                数据交换.dumps(标记数据, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            系统.replace(临时标记, 标记文件)
        finally:
            临时标记.unlink(missing_ok=True)

        with 日志文件.open("a", encoding="utf-8", newline="\n") as 日志:
            日志.write(数据交换.dumps(记录, ensure_ascii=False) + "\n")
            日志.flush()

    return 警告


def _复制缓存元文件(卡片: 视频卡片, 目标目录: 路径) -> _元文件复制结果:
    r"""复制或从 ADB 拉取元文件，并返回文件名及时间戳降级警告。"""
    已复制: list[str] = []
    警告列表: list[str] = []
    ADB路径: str | None = _寻找ADB() if 卡片.来源类型 == "adb" else None

    if 卡片.来源类型 == "adb":
        if not ADB路径 or not 卡片.设备序列号:
            raise RuntimeError("保留元文件时找不到 ADB 设备")

        # Windows ADB 对部分中文完整目标文件路径处理不稳定。先拉到短的
        # ASCII 临时目录，再由 Python 复制到最终归档目录。
        with 临时文件.TemporaryDirectory(prefix="mybiout_metadata_") as 临时目录文本:
            临时目录 = 路径(临时目录文本)
            for 文件名 in _缓存元文件名:
                源路径: str = 卡片.元文件路径表.get(文件名, "")
                if not 源路径:
                    continue
                临时目标文件 = 临时目录 / 文件名
                拉取结果: 子进程.CompletedProcess = _执行ADB(
                    ADB路径,
                    卡片.设备序列号,
                    "pull",
                    "-a",
                    源路径,
                    str(临时目录),
                    超时秒数=60,
                )
                if 拉取结果.returncode != 0:
                    # 保留普通 pull 作为容错，但明确留下不可随程序关闭消失的降级记录。
                    首次错误 = 拉取结果.stderr or 拉取结果.stdout or "ADB 未返回错误文本"
                    警告列表.append(
                        _记录元文件时间戳警告(
                            目标目录,
                            文件名,
                            源路径,
                            首次错误,
                        )
                    )
                    临时目标文件.unlink(missing_ok=True)
                    拉取结果 = _执行ADB(
                        ADB路径,
                        卡片.设备序列号,
                        "pull",
                        源路径,
                        str(临时目录),
                        超时秒数=60,
                    )
                if 拉取结果.returncode != 0 or not 临时目标文件.is_file():
                    错误文本 = (拉取结果.stderr or 拉取结果.stdout or "ADB 未返回错误文本").strip()
                    if 拉取结果.returncode == 0:
                        错误文本 = f"ADB 返回成功，但临时文件未生成；{错误文本}"
                    raise RuntimeError(
                        f"ADB 拉取 {文件名} 失败 (returncode={拉取结果.returncode}): "
                        f"{错误文本[:240]}"
                    )
                文件工具.copy2(临时目标文件, 目标目录 / 文件名)
                已复制.append(文件名)
        return _元文件复制结果(已复制, 警告列表)

    for 文件名 in _缓存元文件名:
        源路径: str = 卡片.元文件路径表.get(文件名, "")
        if not 源路径:
            continue
        目标文件: 路径 = 目标目录 / 文件名
        源文件: 路径 = 路径(源路径)
        if not 源文件.is_file():
            continue
        文件工具.copy2(源文件, 目标文件)
        已复制.append(文件名)
    return _元文件复制结果(已复制, 警告列表)


def _继承本地缓存时间(卡片: 视频卡片, 输出文件: 路径) -> None:
    r"""本地来源尽量让成品继承缓存媒体的访问/修改时间。"""
    if 卡片.来源类型 == "adb":
        return
    try:
        源状态 = 路径(卡片.视频路径).stat()
        系统.utime(输出文件, ns=(源状态.st_atime_ns, 源状态.st_mtime_ns))
    except OSError:
        pass


def _本地合并(卡片: 视频卡片, 输出路径: str) -> None:
    r"""
    本地文件合并，直接使用随包 FFmpeg 显式指定音视频文件。

    :param: card: 视频卡片
    :param: output: 输出 mp4 路径
    :raise: FileNotFoundError: 文件不存在
    :raise: RuntimeError: ffmpeg 合并失败
    """
    视频文件: str = 卡片.视频路径
    音频文件: str = 卡片.音频路径

    if not 视频文件 or not 路径(视频文件).exists():
        raise FileNotFoundError(f"视频文件不存在: {视频文件}")

    if not 音频文件 or not 路径(音频文件).exists():
        raise FileNotFoundError(f"音频文件不存在: {音频文件}")
    _用随包FFmpeg合并(视频文件, 音频文件, 输出路径)


def _导出单个ADB(卡片: 视频卡片, 输出路径: str) -> None:
    r"""
    通过 ADB 拉取视频/音频到临时目录后合并为 mp4
    参考 biliandout DeviceScanner.pull_and_convert ADB 分支
    :param: card: 视频卡片（source_type == "adb"）
    :param: output: 输出 mp4 路径
    :raise: RuntimeError: ADB 不可用或拉取/合并失败
    """
    ADB路径: str | None = _寻找ADB()
    if not ADB路径:
        raise RuntimeError("未找到 ADB 可执行文件")
    序列号: str = 卡片.设备序列号
    if not 序列号:
        raise RuntimeError("ADB 设备序列号为空")

    with 临时文件.TemporaryDirectory() as 临时目录:
        本地视频: str = str(路径(临时目录) / "video.m4s")
        本地音频: str = str(路径(临时目录) / "audio.m4s")

        for 远端文件, 本地文件, 名称 in (
            (卡片.视频路径, 本地视频, "视频"),
            (卡片.音频路径, 本地音频, "音频"),
        ):
            拉取结果: 子进程.CompletedProcess = _执行ADB(
                ADB路径,
                序列号,
                "pull",
                远端文件,
                本地文件,
                超时秒数=300,
            )
            if 拉取结果.returncode != 0:
                错误文本 = (拉取结果.stderr or 拉取结果.stdout or "未知 ADB 错误").strip()
                raise RuntimeError(f"ADB 拉取{名称}失败: {错误文本[:120]}")

        _用随包FFmpeg合并(本地视频, 本地音频, 输出路径)


def _导出单个(卡片: 视频卡片, 输出目录: 路径) -> bool:
    r"""
    导出单个视频（自动区分本地与 ADB 来源）
    :param: card: 视频卡片
    :param: output_dir: 输出目录
    :return: bool: True 表示命中已有导出并跳过，False 表示本次新导出
    """
    文件名文本: str = _构建文件名(卡片)
    if not 文件名文本:
        raise RuntimeError("标题不完整且策略为跳过")
    保留元文件: bool = 工具.取设置("localout", "preserve_metadata") == "true"
    跳过重复: bool = 工具.取设置("localout", "skip_duplicates") != "false"
    身份键: str = _导出身份键(卡片)

    # 同身份任务串行：第一个完成写索引后，后续任务即可直接命中并跳过。
    with _取导出身份锁(身份键):
        if 跳过重复:
            已有输出: 路径 | None = _从索引查找重复(
                输出目录,
                身份键,
                卡片,
                需要元文件=保留元文件,
            )
            if 已有输出 is None:
                已有输出 = _查找旧版同名导出(
                    输出目录,
                    文件名文本,
                    卡片,
                    保留元文件=保留元文件,
                )
            if 已有输出 is not None:
                卡片.输出路径 = str(已有输出)
                return True

        if not _寻找FFmpeg():
            raise RuntimeError("未找到 ffmpeg（请确认绿色包 bin/ 完整）")

        归档目录: 路径 | None = None
        if 保留元文件:
            归档目录, 输出路径 = _预留归档目录(输出目录, 文件名文本)
            预留路径: 路径 = 归档目录
        else:
            输出路径 = _预留输出路径(输出目录, 文件名文本)
            预留路径 = 输出路径

        归档已创建: bool = False
        try:
            if 归档目录 is not None:
                归档目录.mkdir(parents=False, exist_ok=False)
                归档已创建 = True
            if 卡片.来源类型 == "adb":
                _导出单个ADB(卡片, str(输出路径))
            else:
                _本地合并(卡片, str(输出路径))
            _继承本地缓存时间(卡片, 输出路径)
            已复制元文件: list[str] = []
            导出警告列表: list[str] = []
            if 归档目录 is not None:
                元文件结果 = _复制缓存元文件(卡片, 归档目录)
                已复制元文件 = 元文件结果.文件名列表
                导出警告列表 = 元文件结果.警告列表
                卡片.警告 = "；".join(导出警告列表)
            卡片.输出路径 = str(输出路径)
            try:
                _保存导出索引项(
                    输出目录,
                    身份键,
                    输出路径,
                    卡片,
                    已保留元文件=保留元文件,
                    元文件名称列表=已复制元文件,
                    元文件时间戳已保留=not bool(导出警告列表),
                    导出警告列表=导出警告列表,
                )
            except OSError as 异常:
                状态.记录日志("warn", f"视频已导出，但去重索引写入失败: {异常}")
            return False
        except Exception:
            输出路径.unlink(missing_ok=True)
            if 归档目录 is not None and 归档已创建:
                with 忽略异常(OSError):
                    文件工具.rmtree(归档目录)
            raise
        finally:
            _释放输出路径(预留路径)


def _导出线程函数(卡片编号列表: list[str]) -> None:
    r"""
    导出线程入口函数
    :param: card_ids: 待导出的卡片 ID 列表
    """
    try:
        输出目录: 路径 = 工具.取导出路径() / 工具.取设置("localout", "folder")
        输出目录.mkdir(parents=True, exist_ok=True)
        并发数: int = max(
            1,
            min(_安全整数(工具.取设置("localout", "ffmpeg_concurrent") or "3", 3), 32),
        )

        with 状态.锁:
            编号集合 = set(卡片编号列表)
            目标列表: list[视频卡片] = [
                卡片项
                for 卡片项 in 状态.任务卡片列表
                if 卡片项.编号 in 编号集合 and 卡片项.状态名 in {"queued", "failed"}
            ]
            状态.导出总数 = len(目标列表)

        状态.记录日志("info", f"开始导出 {len(目标列表)} 个视频 (并发 {并发数})")

        def _导出一个(卡片: 视频卡片) -> None:
            if 状态._导出取消.is_set():
                return
            with 状态.锁:
                卡片.状态名 = "exporting"
                卡片.错误 = ""
            状态.记录日志("info", f"导出中: {卡片.标题 or 卡片.文件夹名}")
            try:
                已跳过: bool = _导出单个(卡片, 输出目录)
                with 状态.锁:
                    卡片.状态名 = "skipped" if 已跳过 else "success"
                    状态.任务卡片列表 = [
                        卡片项
                        for 卡片项 in 状态.任务卡片列表
                        if 卡片项.编号 != 卡片.编号
                    ]
                    状态.完成卡片列表.append(卡片)
                    状态.导出完成数 += 1
                    if 已跳过:
                        状态.导出跳过数 += 1
                    else:
                        状态.导出成功数 += 1
                    状态.导出进度 = (
                        状态.导出完成数 / 状态.导出总数 if 状态.导出总数 else 1
                    )
                if 已跳过:
                    状态.记录日志(
                        "info",
                        f"跳过重复: {卡片.标题 or 卡片.文件夹名}（已有 {卡片.输出路径}）",
                    )
                else:
                    状态.记录日志("success", f"导出完成: {卡片.标题 or 卡片.文件夹名}")
            except Exception as e:
                with 状态.锁:
                    卡片.状态名 = "failed"
                    卡片.错误 = str(e)
                    状态.导出完成数 += 1
                    状态.导出失败数 += 1
                    状态.导出进度 = (
                        状态.导出完成数 / 状态.导出总数 if 状态.导出总数 else 1
                    )
                状态.记录日志("error", f"导出失败: {卡片.标题 or 卡片.文件夹名} — {e}")

        with 线程池执行器(max_workers=并发数) as 卡片池:
            任务映射: dict = {
                卡片池.submit(_导出一个, 卡片项): 卡片项 for 卡片项 in 目标列表
            }
            for _ in 逐个完成(任务映射):
                pass

        with 状态.锁:
            成功数 = 状态.导出成功数
            跳过数 = 状态.导出跳过数
            失败数 = 状态.导出失败数
            总数 = 状态.导出总数
            未开始数 = max(0, 总数 - 状态.导出完成数)
        if 状态._导出取消.is_set():
            状态.记录日志(
                "warn",
                f"导出已取消 (新增 {成功数}，跳过 {跳过数}，失败 {失败数}，未开始 {未开始数})",
            )
        elif 失败数:
            状态.记录日志(
                "warn",
                f"导出结束 (成功 {成功数}，失败 {失败数}；新增 {成功数}，跳过 {跳过数}，共 {总数})",
            )
        else:
            状态.记录日志(
                "success",
                f"全部导出任务结束 (新增 {成功数}，跳过 {跳过数}，共 {总数})",
            )
    except Exception as e:
        状态.记录日志("error", f"导出线程异常: {e}")
    finally:
        with 状态.锁:
            状态.导出状态 = "idle"
            状态._导出取消.clear()


# ===== 公开 API =====


def 取状态() -> dict:
    r"""
    获取当前状态快照
    :return: dict
    """
    return 状态.快照()


def 取环境状态() -> dict:
    r"""
    获取环境状态信息，用于前端显示诊断
    :return: dict: 环境状态
    """
    ADB路径值: str | None = _寻找ADB()
    FFmpeg路径值: str | None = _寻找FFmpeg()
    有网络请求: bool = _有网络请求
    ADB名称: str = "adb.exe 与 AdbWinApi.dll" if 系统信息.platform == "win32" else "adb"
    FFmpeg名称: str = "ffmpeg.exe" if 系统信息.platform == "win32" else "ffmpeg"

    return {
        "adb": {
            "available": ADB路径值 is not None,
            "path": ADB路径值 or "",
            "hint": f"绿色包应自带 bin/{ADB名称}" if not ADB路径值 else "",
        },
        "ffmpeg": {
            "available": FFmpeg路径值 is not None,
            "path": FFmpeg路径值 or "",
            "hint": f"绿色包应自带 bin/{FFmpeg名称}" if not FFmpeg路径值 else "",
        },
        "httpx": {
            "available": 有网络请求,
            "hint": "爬虫补全功能不可用（可选依赖）" if not 有网络请求 else "",
        },
    }


def 取可用来源() -> dict:
    r"""
    获取可用的扫描源列表
    包括：浏览按钮 / PC 缓存 / 挂载驱动器 Android 设备 / ADB Android 设备
    参考 biliandout DeviceScanner.get_connected_devices
    :return: dict: 包含 sources 列表和 warnings 列表
    """
    警告列表: list[str] = []
    来源列表: list[dict] = [
        {
            "id": "browse",
            "label": "浏览本地路径...",
            "icon": "📂",
            "type": "browse",
            "path": "",
            "serial": "",
            "package": "",
        },
    ]

    # 环境检查
    if not _寻找FFmpeg():
        警告列表.append("ffmpeg 未找到，导出功能将不可用")

    ADB路径值: str | None = _寻找ADB()
    if not ADB路径值:
        警告列表.append("ADB 未找到，无法扫描 Android 设备（USB调试模式）")

    # PC 桌面端缓存：即使发布配置不携带本机路径，也会发现默认客户端目录。
    for 序号, 电脑缓存目录 in enumerate(_取电脑端缓存路径(), start=1):
        来源列表.append(
            {
                "id": f"pc_cache_{序号}",
                "label": "哔哩哔哩桌面端缓存" if 序号 == 1 else f"哔哩哔哩桌面端缓存 {序号}",
                "icon": "💻",
                "type": "pc",
                "path": str(电脑缓存目录),
                "serial": "",
                "package": "",
            }
        )

    # 挂载为本地驱动器的 Android 设备（MTP / USB 大容量存储）
    # 参考 biliandout DeviceScanner.get_drive_devices
    驱动器数量: int = 0
    for 盘符 in "DEFGHIJKLMNOPQRSTUVWXYZ":
        驱动器: 路径 = 路径(f"{盘符}:/")
        if not 驱动器.exists():
            continue
        安卓数据目录: 路径 = 驱动器 / "Android" / "data"
        if not 安卓数据目录.exists():
            continue
        设备名称: str = _取卷标(盘符)
        for 包名项, 名称 in _哔哩包列表:
            for 下载路径 in (
                安卓数据目录 / 包名项 / "download",
                安卓数据目录 / 包名项 / "files" / "download",
            ):
                if 下载路径.exists():
                    来源列表.append(
                        {
                            "id": f"drive_{盘符}_{包名项}",
                            "label": f"{设备名称} 上的{名称}",
                            "icon": "📱",
                            "type": "drive",
                            "path": str(下载路径),
                            "serial": "",
                            "package": 包名项,
                        }
                    )
                    驱动器数量 += 1
                    break

    # ADB 连接的 Android 设备（USB 调试模式）
    # 参考 biliandout DeviceScanner.get_adb_devices
    ADB设备列表: list[tuple[str, str]] = _取ADB设备列表() if ADB路径值 else []
    if ADB路径值 and not ADB设备列表:
        警告列表.append("ADB 已安装但未检测到设备，请确认设备已启用 USB 调试并已授权")

    for 序列号, 显示名称 in ADB设备列表:
        for 包名项, 名称 in _取ADB已安装哔哩包(ADB路径值, 序列号):
            来源列表.append(
                {
                    "id": f"adb_{序列号}_{包名项}",
                    "label": f"{显示名称} · {名称}（ADB）",
                    "icon": "🔌",
                    "type": "adb",
                    "path": "",
                    "serial": 序列号,
                    "package": 包名项,
                }
            )

    当前时间: float = 时间.time()
    if 当前时间 - 状态._上次可用刷新 >= 1.0:
        with 状态.锁:
            状态._上次可用刷新 = 当前时间
            状态._可用键集合 = {
                f"{来源项.get('type', '')}|{来源项.get('label', '')}" for 来源项 in 来源列表 if 来源项.get("type") in ("drive", "adb")
            }

    return {"sources": 来源列表, "warnings": 警告列表}


def 浏览本地() -> str | None:
    r"""
    弹出文件夹对话框选择本地缓存目录
    :return: str | None
    """
    try:
        from tkinter import Tk
        from tkinter import filedialog as 文件对话框

        根目录: Tk = Tk()
        根目录.withdraw()
        根目录.attributes("-topmost", True)
        文件夹: str = 文件对话框.askdirectory(title="选择缓存目录")
        根目录.destroy()
        return 文件夹 if 文件夹 else None
    except Exception:
        return None


def 浏览恢复归档() -> str | None:
    r"""弹出文件夹对话框选择包含一个或多个元文件归档的目录。"""
    try:
        from tkinter import Tk
        from tkinter import filedialog as 文件对话框

        根目录: Tk = Tk()
        根目录.withdraw()
        根目录.attributes("-topmost", True)
        文件夹: str = 文件对话框.askdirectory(title="选择 MyBiOut 归档文件夹或其上级目录")
        根目录.destroy()
        return 文件夹 if 文件夹 else None
    except Exception:
        return None


def 检查恢复归档(归档路径: str) -> dict:
    r"""检查归档完整性并返回将要生成的缓存坐标。"""
    try:
        归档 = _检查恢复归档(_安全文本(归档路径))
        return {"ok": True, "archive": 归档.转字典()}
    except Exception as 异常:
        return {"ok": False, "error": str(异常)}


def 扫描恢复归档(根目录路径: str) -> dict:
    r"""递归扫描恢复归档，索引文件存在与否均不影响识别。"""
    try:
        归档列表, 警告列表 = _扫描恢复归档目录(_安全文本(根目录路径))
        with 状态.锁:
            if 状态._恢复线程 is None or not 状态._恢复线程.is_alive():
                状态.恢复状态 = "idle"
                状态.恢复进度 = 0.0
                状态.恢复消息 = ""
                状态.恢复错误 = ""
                状态.恢复目标路径 = ""
                状态.恢复项目列表 = []
                状态.恢复总数 = 0
                状态.恢复完成数 = 0
                状态.恢复成功数 = 0
                状态.恢复跳过数 = 0
                状态.恢复失败数 = 0
        return {
            "ok": True,
            "archives": [归档.转字典() for 归档 in 归档列表],
            "warnings": 警告列表,
        }
    except Exception as 异常:
        return {"ok": False, "archives": [], "warnings": [], "error": str(异常)}


def _ADB目录存在(ADB路径: str, 序列号: str, 目录: str) -> bool:
    try:
        结果 = _执行ADB(
            ADB路径,
            序列号,
            "shell",
            f"test -d {命令行转义.quote(目录)}",
            超时秒数=12,
        )
        return 结果.returncode == 0
    except Exception:
        return False


def 取恢复设备列表() -> dict:
    r"""返回已授权、安装了受支持客户端且缓存目录可写入的 ADB 设备。"""
    ADB路径: str | None = _寻找ADB()
    if not ADB路径:
        return {"devices": [], "warnings": ["未找到 ADB，无法导入手机"]}

    设备列表: list[dict] = []
    警告列表: list[str] = []
    ADB设备列表 = _取ADB设备列表()
    if not ADB设备列表:
        return {"devices": [], "warnings": ["未检测到已授权的 ADB 设备"]}

    for 序列号, 显示名称 in ADB设备列表:
        已安装包列表 = _取ADB已安装哔哩包(ADB路径, 序列号)
        if not 已安装包列表:
            警告列表.append(f"{显示名称} 未安装受支持的哔哩哔哩客户端")
            continue
        for 包名, 客户端名称 in 已安装包列表:
            找到布局 = False
            for 缓存布局 in ("download", "files/download"):
                手机路径 = f"/sdcard/Android/data/{包名}/{缓存布局}"
                if not _ADB目录存在(ADB路径, 序列号, 手机路径):
                    continue
                找到布局 = True
                设备列表.append(
                    {
                        "id": f"{序列号}|{包名}|{缓存布局}",
                        "serial": 序列号,
                        "device_name": 显示名称,
                        "package": 包名,
                        "app_name": 客户端名称,
                        "layout": 缓存布局,
                        "path": 手机路径,
                        "label": f"{显示名称} · {客户端名称}",
                    }
                )
            if not 找到布局:
                警告列表.append(f"{显示名称} · {客户端名称} 尚未生成 download 缓存目录")
    return {"devices": 设备列表, "warnings": 警告列表}


def _更新恢复进度(进度: float, 消息: str) -> None:
    需要记录日志 = False
    with 状态.锁:
        状态.恢复进度 = 进度
        状态.恢复消息 = 消息
        if 消息 and 消息 != 状态._恢复上次消息:
            状态._恢复上次消息 = 消息
            需要记录日志 = True
    if 需要记录日志:
        状态.记录日志("info", f"缓存恢复: {消息}")


def _更新恢复项目(
    项目编号集合: set[str],
    状态名: str,
    消息: str = "",
    目标路径: str = "",
) -> None:
    with 状态.锁:
        for 项目 in 状态.恢复项目列表:
            if 项目.get("id") not in 项目编号集合:
                continue
            项目["status"] = 状态名
            项目["message"] = 消息
            if 目标路径:
                项目["target_path"] = 目标路径
        终态 = {"success", "skipped", "failed", "cancelled"}
        状态.恢复完成数 = sum(1 for 项目 in 状态.恢复项目列表 if 项目.get("status") in 终态)
        状态.恢复成功数 = sum(1 for 项目 in 状态.恢复项目列表 if 项目.get("status") == "success")
        状态.恢复跳过数 = sum(1 for 项目 in 状态.恢复项目列表 if 项目.get("status") == "skipped")
        状态.恢复失败数 = sum(1 for 项目 in 状态.恢复项目列表 if 项目.get("status") == "failed")


def _恢复线程函数(归档列表: list, 序列号: str, 包名: str, 缓存布局: str) -> None:
    try:
        FFmpeg路径 = _寻找FFmpeg()
        ADB路径 = _寻找ADB()
        if not FFmpeg路径:
            raise RuntimeError("未找到 ffmpeg（请确认绿色包 bin/ 完整）")
        if not ADB路径:
            raise RuntimeError("未找到 ADB（请确认绿色包 bin/ 完整）")

        稿件分组: dict[str, list] = {}
        for 归档 in 归档列表:
            稿件分组.setdefault(归档.稿件号, []).append(归档)
        总组数 = max(1, len(稿件分组))
        状态.记录日志(
            "info",
            f"开始批量恢复 {len(归档列表)} 个归档，共 {len(稿件分组)} 个 avid",
        )
        已导入目标: list[str] = []
        with 临时文件.TemporaryDirectory(prefix="mybiout_restore_") as 临时目录:
            for 组序号, (稿件号, 组内归档) in enumerate(稿件分组.items()):
                项目编号集合 = {归档.标识 for 归档 in 组内归档}
                if 状态._恢复取消.is_set():
                    _更新恢复项目(项目编号集合, "cancelled", "已取消，尚未处理")
                    continue

                _更新恢复项目(项目编号集合, "restoring", f"正在重建 av{稿件号}")
                状态.记录日志("info", f"正在恢复 av{稿件号}，包含 {len(组内归档)} 个分集")

                def 重建进度(进度: float, 消息: str, *, _组序号: int = 组序号) -> None:
                    总进度 = (_组序号 + 0.56 * 进度) / 总组数
                    _更新恢复进度(总进度, 消息)

                def 导入进度(进度: float, 消息: str, *, _组序号: int = 组序号) -> None:
                    归一进度 = max(0.0, min(1.0, (进度 - 0.64) / 0.36))
                    总进度 = (_组序号 + 0.56 + 0.44 * 归一进度) / 总组数
                    _更新恢复进度(总进度, 消息)

                try:
                    缓存目录 = 重建缓存组(组内归档, 临时目录, FFmpeg路径, 重建进度)
                    手机路径 = 导入缓存到手机(
                        缓存目录,
                        ADB路径,
                        序列号,
                        包名,
                        缓存布局,
                        导入进度,
                    )
                    已导入目标.append(手机路径)
                    _更新恢复项目(项目编号集合, "success", "恢复与导入完成", 手机路径)
                    状态.记录日志("success", f"缓存已恢复到手机: {手机路径}")
                except 缓存已存在错误 as 异常:
                    _更新恢复项目(项目编号集合, "skipped", str(异常))
                    状态.记录日志("warn", f"跳过 av{稿件号}: {异常}")
                except Exception as 异常:
                    _更新恢复项目(项目编号集合, "failed", str(异常))
                    状态.记录日志("error", f"恢复 av{稿件号} 失败: {异常}")

        with 状态.锁:
            有取消 = any(项目.get("status") == "cancelled" for 项目 in 状态.恢复项目列表)
            有问题 = 状态.恢复失败数 > 0 or 状态.恢复跳过数 > 0
            状态.恢复状态 = "cancelled" if 有取消 else "partial" if 有问题 else "success"
            状态.恢复进度 = 1.0
            状态.恢复消息 = (
                f"批量恢复结束：成功 {状态.恢复成功数}，跳过 {状态.恢复跳过数}，失败 {状态.恢复失败数}"
            )
            状态.恢复错误 = "" if 状态.恢复失败数 == 0 else "部分归档恢复失败，请查看列表"
            状态.恢复目标路径 = "；".join(已导入目标)
        状态.记录日志("success" if 状态.恢复失败数 == 0 else "warn", 状态.恢复消息)
    except Exception as 异常:
        with 状态.锁:
            未完成编号 = {
                str(项目.get("id"))
                for 项目 in 状态.恢复项目列表
                if 项目.get("status") in {"queued", "restoring"}
            }
        _更新恢复项目(未完成编号, "failed", str(异常))
        with 状态.锁:
            状态.恢复状态 = "error"
            状态.恢复消息 = "恢复失败"
            状态.恢复错误 = str(异常)
            状态.恢复目标路径 = ""
        状态.记录日志("error", f"缓存恢复失败: {异常}")
    finally:
        with 状态.锁:
            状态._恢复线程 = None
        状态._恢复取消.clear()


def 开始批量恢复(归档路径列表: list[str], 序列号: str, 包名: str, 缓存布局: str) -> dict:
    r"""校验批量选择并启动后台恢复线程。"""
    序列号 = _安全文本(序列号)
    包名 = _安全文本(包名)
    缓存布局 = _安全文本(缓存布局)
    if 包名 not in _哔哩包名表:
        return {"ok": False, "error": f"不支持的哔哩哔哩客户端: {包名}"}
    if 缓存布局 not in {"download", "files/download"}:
        return {"ok": False, "error": f"不支持的缓存布局: {缓存布局}"}

    可用设备集合 = {
        (设备["serial"], 设备["package"], 设备["layout"])
        for 设备 in 取恢复设备列表()["devices"]
    }
    if (序列号, 包名, 缓存布局) not in 可用设备集合:
        return {"ok": False, "error": "目标设备已离线、未授权或缓存目录不可用"}

    去重路径列表 = list(dict.fromkeys(_安全文本(路径项) for 路径项 in 归档路径列表 if _安全文本(路径项)))
    if not 去重路径列表:
        return {"ok": False, "error": "没有选择可恢复的归档"}

    归档列表: list = []
    项目列表: list[dict] = []
    for 归档路径 in 去重路径列表:
        try:
            归档 = _检查恢复归档(归档路径)
            归档列表.append(归档)
            项目 = 归档.转字典()
            项目.update({"status": "queued", "message": "等待恢复", "target_path": ""})
        except Exception as 异常:
            项目 = {
                "id": f"invalid-{哈希.sha256(归档路径.encode('utf-8')).hexdigest()[:20]}",
                "path": 归档路径,
                "title": 路径(归档路径).name or 归档路径,
                "avid": "",
                "cache_path": "",
                "mp4_name": "",
                "size_bytes": 0,
                "size_mb": 0,
                "status": "failed",
                "message": str(异常),
                "target_path": "",
            }
        项目列表.append(项目)
    if not 归档列表:
        return {"ok": False, "error": "选择的归档均已失效或不完整"}

    with 状态.锁:
        if 状态._恢复线程 is not None and 状态._恢复线程.is_alive():
            return {"ok": False, "error": "已有缓存恢复任务正在进行"}
        状态.恢复状态 = "restoring"
        状态.恢复进度 = 0.0
        状态.恢复消息 = "准备恢复"
        状态.恢复错误 = ""
        状态.恢复目标路径 = ""
        状态.恢复项目列表 = 项目列表
        状态.恢复总数 = len(项目列表)
        状态.恢复完成数 = sum(1 for 项目 in 项目列表 if 项目["status"] == "failed")
        状态.恢复成功数 = 0
        状态.恢复跳过数 = 0
        状态.恢复失败数 = 状态.恢复完成数
        状态._恢复上次消息 = ""
        状态._恢复取消.clear()
        线程对象 = 线程.Thread(
            target=_恢复线程函数,
            args=(归档列表, 序列号, 包名, 缓存布局),
            daemon=True,
        )
        状态._恢复线程 = 线程对象
    try:
        线程对象.start()
    except Exception:
        with 状态.锁:
            状态.恢复状态 = "error"
            状态._恢复线程 = None
        raise
    return {"ok": True, "total": len(项目列表), "valid": len(归档列表)}


def 开始恢复(归档路径: str, 序列号: str, 包名: str, 缓存布局: str) -> dict:
    r"""兼容原单项恢复接口。"""
    return 开始批量恢复([归档路径], 序列号, 包名, 缓存布局)


def 取消恢复() -> dict:
    r"""请求在当前 avid 处理完成后停止后续批量恢复。"""
    with 状态.锁:
        if 状态._恢复线程 is None or not 状态._恢复线程.is_alive():
            return {"ok": False, "error": "当前没有正在进行的恢复任务"}
        状态._恢复取消.set()
        状态.恢复消息 = "正在完成当前缓存，之后将停止"
    状态.记录日志("warn", "已请求取消批量恢复")
    return {"ok": True}


def 添加来源(
    来源类型: str,
    路径文本: str = "",
    标签: str = "",
    序列号: str = "",
    包名: str = "",
) -> dict:
    r"""
    添加扫描源并启动扫描线程
    :param: source_type: 来源类型
    :param: path: 扫描路径（adb 时为空）
    :param: label: 来源标签
    :param: serial: ADB 设备序列号
    :param: package: 应用包名
    :return: dict
    """
    来源类型 = 来源类型.strip().lower()
    路径文本 = 路径文本.strip()
    标签 = 标签.strip()
    序列号 = 序列号.strip()
    包名 = 包名.strip()

    if 来源类型 not in {"pc", "drive", "adb", "local"}:
        return {"ok": False, "error": f"未知扫描源类型: {来源类型}"}

    if 来源类型 == "adb":
        if not 序列号:
            return {"ok": False, "error": "ADB 设备序列号为空"}
        if 包名 and 包名 not in _哔哩包名表:
            return {"ok": False, "error": f"未知 B 站包名: {包名}"}
        ADB路径值: str | None = _寻找ADB()
        if not ADB路径值:
            return {"ok": False, "error": "未找到 ADB 可执行文件"}
        在线序列号集合 = {设备序列号 for 设备序列号, _ in _取ADB设备列表()}
        if 序列号 not in 在线序列号集合:
            return {"ok": False, "error": f"ADB 设备已离线或未授权: {序列号}"}
        if 包名:
            已安装包集合 = {
                已安装包名 for 已安装包名, _ in _取ADB已安装哔哩包(ADB路径值, 序列号)
            }
            if 包名 not in 已安装包集合:
                return {"ok": False, "error": f"设备未安装对应 B 站客户端: {包名}"}
    else:
        if not 路径文本 or not 路径(路径文本).is_dir():
            return {"ok": False, "error": f"路径不存在: {路径文本 or '(空)'}"}

    线程对象: 线程.Thread = 线程.Thread(
        target=_扫描线程函数,
        args=(来源类型, 路径文本, 标签 or 路径文本 or 来源类型, 序列号, 包名),
        daemon=True,
    )
    with 状态.锁:
        if 状态.扫描状态 != "idle" or (
            状态._扫描线程 is not None and 状态._扫描线程.is_alive()
        ):
            return {"ok": False, "error": "已有扫描在进行中或正在取消"}
        状态._扫描取消.clear()
        状态._扫描暂停.clear()
        状态.扫描状态 = "scanning"
        状态.扫描进度 = 0.0
        状态._扫描线程 = 线程对象
    try:
        线程对象.start()
    except Exception:
        with 状态.锁:
            状态.扫描状态 = "idle"
            状态._扫描线程 = None
        raise
    return {"ok": True}


def 暂停扫描() -> None:
    已暂停: bool = False
    with 状态.锁:
        if 状态.扫描状态 == "scanning":
            状态._扫描暂停.set()
            状态.扫描状态 = "paused"
            已暂停 = True
    if 已暂停:
        状态.记录日志("info", "扫描已暂停")


def 继续扫描() -> None:
    已继续: bool = False
    with 状态.锁:
        if 状态.扫描状态 == "paused":
            状态._扫描暂停.clear()
            状态.扫描状态 = "scanning"
            已继续 = True
    if 已继续:
        状态.记录日志("info", "扫描已继续")


def 取消扫描() -> None:
    正在取消: bool = False
    with 状态.锁:
        if 状态.扫描状态 != "idle":
            状态._扫描取消.set()
            状态._扫描暂停.clear()
            状态.扫描状态 = "cancelling"
            正在取消 = True
    if 正在取消:
        状态.记录日志("info", "正在取消扫描...")


def 加入任务(卡片编号列表: list[str]) -> dict:
    r"""
    将源卡片添加到任务栏
    :param: card_ids: 源卡片 ID 列表
    :return: dict
    """
    添加数量: int = 0
    with 状态.锁:
        已有集合: set[str] = {状态._去重键(卡片项) for 卡片项 in 状态.任务卡片列表}
        for 来源编号 in 卡片编号列表:
            for 来源卡片 in 状态.来源卡片列表:
                if 来源卡片.编号 == 来源编号:
                    键: str = 状态._去重键(来源卡片)
                    if 键 not in 已有集合:
                        状态.任务卡片列表.append(来源卡片.克隆())
                        已有集合.add(键)
                        添加数量 += 1
                    break
    状态.记录日志("info", f"已添加 {添加数量} 个视频到任务栏")
    return {"ok": True, "added": 添加数量}


def 移除来源卡片(卡片编号列表: list[str]) -> None:
    r"""
    移除指定源卡片
    :param: card_ids: 卡片 ID 列表
    """
    编号集合: set[str] = set(卡片编号列表)
    with 状态.锁:
        移除列表: list[视频卡片] = [卡片项 for 卡片项 in 状态.来源卡片列表 if 卡片项.编号 in 编号集合]
        状态.来源卡片列表 = [卡片项 for 卡片项 in 状态.来源卡片列表 if 卡片项.编号 not in 编号集合]
        for 卡片项 in 移除列表:
            状态._已知键集合.discard(状态._去重键(卡片项))


def 移除任务卡片(卡片编号列表: list[str]) -> None:
    r"""
    移除指定任务卡片
    :param: card_ids: 卡片 ID 列表
    """
    编号集合: set[str] = set(卡片编号列表)
    with 状态.锁:
        状态.任务卡片列表 = [卡片项 for 卡片项 in 状态.任务卡片列表 if 卡片项.编号 not in 编号集合]


def 清空来源() -> None:
    with 状态.锁:
        状态.来源卡片列表.clear()
        状态._已知键集合.clear()
    状态.记录日志("info", "源栏已清空")


def 清空任务() -> None:
    with 状态.锁:
        状态.任务卡片列表 = [卡片项 for 卡片项 in 状态.任务卡片列表 if 卡片项.状态名 == "exporting"]
    状态.记录日志("info", "任务栏已清空 (导出中的任务保留)")


def 清空完成() -> None:
    with 状态.锁:
        状态.完成卡片列表.clear()
    状态.记录日志("info", "完成栏已清空")


def 开始导出(卡片编号列表: list[str]) -> dict:
    r"""
    开始导出任务
    :param: card_ids: 待导出卡片 ID，为空则导出全部排队中的任务
    :return: dict
    """
    with 状态.锁:
        if 状态.导出状态 != "idle" or (
            状态._导出线程 is not None and 状态._导出线程.is_alive()
        ):
            return {"ok": False, "error": "导出正在进行中"}
        if not 卡片编号列表:
            卡片编号列表 = [卡片项.编号 for 卡片项 in 状态.任务卡片列表 if 卡片项.状态名 == "queued"]
        可导出编号集合 = {
            卡片项.编号
            for 卡片项 in 状态.任务卡片列表
            if 卡片项.编号 in set(卡片编号列表)
            and 卡片项.状态名 in {"queued", "failed"}
        }
        卡片编号列表 = [编号 for 编号 in 卡片编号列表 if 编号 in 可导出编号集合]
        if not 卡片编号列表:
            return {"ok": False, "error": "没有可导出的任务"}
        状态._导出取消.clear()
        状态.导出状态 = "exporting"
        状态.导出总数 = len(卡片编号列表)
        状态.导出完成数 = 0
        状态.导出成功数 = 0
        状态.导出跳过数 = 0
        状态.导出失败数 = 0
        状态.导出进度 = 0.0
        线程对象: 线程.Thread = 线程.Thread(
            target=_导出线程函数,
            args=(卡片编号列表,),
            daemon=True,
        )
        状态._导出线程 = 线程对象
    try:
        线程对象.start()
    except Exception:
        with 状态.锁:
            状态.导出状态 = "idle"
            状态._导出线程 = None
        raise
    return {"ok": True}


def 取消导出() -> None:
    with 状态.锁:
        正在导出 = 状态.导出状态 == "exporting"
        if 正在导出:
            状态._导出取消.set()
    if 正在导出:
        状态.记录日志("info", "正在取消导出...")


def 取封面字节(卡片编号: str) -> tuple[bytes, str] | None:
    r"""
    根据卡片 id 取出封面字节
    :param: card_id: 卡片 id
    :return: (字节, content-type) 或 None
    """
    with 状态.锁:
        卡片池: list[视频卡片] = 状态.来源卡片列表 + 状态.任务卡片列表 + 状态.完成卡片列表
        for 卡片项 in 卡片池:
            if 卡片项.编号 != 卡片编号 or not 卡片项.封面路径:
                continue
            封面文件: 路径 = 路径(卡片项.封面路径)
            if not 封面文件.exists():
                continue
            后缀: str = 封面文件.suffix.lower()
            内容类型: str = "image/jpeg" if 后缀 in (".jpg", ".jpeg") else "image/png"
            try:
                return 封面文件.read_bytes(), 内容类型
            except OSError:
                return None
    return None
