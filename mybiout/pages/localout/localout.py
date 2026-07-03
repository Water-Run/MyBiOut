r"""
LocalOut! 本地缓存导出服务层, 负责扫描、解析和导出本地视频缓存

:file: mybiout/pages/localout/localout.py
:author: WaterRun
:time: 2026-04-12
"""

import ctypes as 系统接口
import hashlib as 哈希
import json as 数据交换
import os as 系统
import re as 正则
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

try:
    import httpx as 网络请求

    _有网络请求: bool = True
except Exception:
    网络请求 = None
    _有网络请求: bool = False

try:
    from biliffm4s import biliffm4s as _缓存合并库

    _有合并库: bool = True
except Exception:
    _缓存合并库 = None
    _有合并库: bool = False

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


# ===== ADB 工具 =====


def _寻找ADB() -> str | None:
    r"""
    查找 adb 可执行文件路径（参考 biliandout DeviceScanner.find_adb）
    :return: str | None: 路径, 未找到返回 None
    """
    程序名: str = "adb.exe" if 系统信息.platform == "win32" else "adb"
    if 文件工具.which(程序名) or 文件工具.which("adb"):
        return 程序名
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
        ):
            if 候选路径.exists():
                return str(候选路径)
    return None


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
    return 名称[:200] if 名称 else "untitled"


def _兆字节(字节数: int | float) -> float:
    return round(字节数 / 1048576, 1) if 字节数 else 0


# ===== 数据模型 =====


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
    输出路径: str = ""
    状态名: str = "queued"
    错误: str = ""

    def __post_init__(自身) -> None:
        自身.AV号 = str(自身.AV号)
        自身.分集序号 = int(自身.分集序号)
        自身.字节数 = int(自身.字节数)

    def 转字典(自身) -> dict:
        仍存在: bool = True
        if 自身.来源类型 in ("local", "pc", "drive") and 自身.视频路径:
            仍存在 = 路径(自身.视频路径).exists()
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
            "video_path": 自身.视频路径,
            "output_path": 自身.输出路径,
            "path_display": 自身.输出路径 or str(路径(自身.视频路径).parent if 自身.视频路径 else ""),
            "alive": 仍存在,
            "status": 自身.状态名,
            "error": 自身.错误,
        }

    def 克隆(自身) -> 视频卡片:
        return 替换数据(自身, 编号=_生成编号(), 状态名="queued", 错误="", 输出路径="")


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
        自身._扫描线程: 线程.Thread | None = None
        自身._扫描取消: 线程.Event = 线程.Event()
        自身._扫描暂停: 线程.Event = 线程.Event()
        自身._导出线程: 线程.Thread | None = None
        自身._导出取消: 线程.Event = 线程.Event()
        自身._已知键集合: set[str] = set()
        自身._可用键集合: set[str] = set()
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

    页面数据: dict = 数据.get("page_data") or {}
    宽度: int = 页面数据.get("width", 0)
    高度: int = 页面数据.get("height", 0)
    类型标记: str = str(数据.get("type_tag", ""))
    父目录: 路径 = 路径文本.parent

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
        标题=数据.get("title", ""),
        BV号=数据.get("bvid", "") or "",
        AV号=str(数据.get("avid", "")),
        UP主名称=数据.get("owner_name", ""),
        分集序号=页面数据.get("page", 1),
        清晰度=数据.get("quality_pithy_description", ""),
        分辨率=f"{宽度}×{高度}" if 宽度 and 高度 else "",
        字节数=数据.get("total_bytes", 0),
        文件夹名=父目录.name,
        来源标签=来源标签,
        来源类型=来源类型,
        设备序列号=序列号,
        视频路径=视频路径,
        音频路径=音频路径,
        封面路径=_向上寻找封面(父目录),
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

    清晰度编号: int = 数据.get("qn", 0)
    发布时间戳: int = 数据.get("pubdate", 0)
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
        AV号=str(数据.get("aid", "") or ""),
        UP主名称=数据.get("uname", ""),
        合集标题=数据.get("groupTitle", "") or "",
        分集序号=数据.get("p", 1),
        清晰度=_清晰度映射.get(清晰度编号, str(清晰度编号) if 清晰度编号 else ""),
        字节数=数据.get("totalSize", 0),
        发布时间=发布时间,
        文件夹名=缓存目录.name,
        来源标签=来源标签,
        来源类型="pc",
        视频路径=视频路径,
        音频路径=音频路径,
        封面路径=_向上寻找封面(缓存目录),
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
    宽度: int = int(视频项.get("width", 0) or 0)
    高度: int = int(视频项.get("height", 0) or 0)
    分辨率: str = f"{宽度}×{高度}" if 宽度 and 高度 else ""
    帧率: str = ""
    if 帧率值 := 视频项.get("frame_rate"):
        try:
            文件: float = float(帧率值)
            帧率 = f"{文件:.0f}fps" if 文件 == int(文件) else f"{文件:.1f}fps"
        except ValueError, TypeError:
            pass
    return 分辨率, 帧率, int(视频项.get("bandwidth", 0) or 0)


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
    )


def _爬虫补全(卡片: 视频卡片) -> None:
    r"""
    若设置启用爬虫降级, 当卡片缺失关键元数据(title/up)时, 尝试用 BV 号补全
    :param: card: 待补全卡片 (就地修改)
    """
    超时秒数: float | None = 工具.取爬虫兜底超时()
    if 超时秒数 is None or not _有网络请求:
        return
    if 卡片.标题 and 卡片.UP主名称:
        return
    if not 卡片.BV号:
        if 匹配 := 正则.search(r"(BV[\w]{10,})", 卡片.文件夹名 or ""):
            卡片.BV号 = 匹配.group(1)
        else:
            return
    try:
        with 网络请求.Client(headers=_爬虫请求头, timeout=超时秒数) as 卡片项:
            响应 = 卡片项.get(
                "https://api.bilibili.com/x/web-interface/view",
                params={"bvid": 卡片.BV号},
            )
            数据: dict = 响应.json()
        if 数据.get("code") != 0:
            return
        信息: dict = 数据.get("data", {})
        if not 卡片.标题:
            卡片.标题 = 信息.get("title", "")
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
        if (卡片项 := _解析入口JSON(入口文件, 来源标签, "local")) and 状态.添加来源卡片(卡片项):
            卡片列表.append(卡片项)
        if 总数:
            with 状态.锁:
                状态.扫描进度 = (序号 + 1) / 总数

    for 序号, 视频信息文件 in enumerate(视频信息文件列表):
        if 状态._扫描取消.is_set():
            break
        while 状态._扫描暂停.is_set() and not 状态._扫描取消.is_set():
            时间.sleep(0.2)
        if (卡片项 := _解析视频信息JSON(视频信息文件, 来源标签)) and 状态.添加来源卡片(卡片项):
            卡片列表.append(卡片项)
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
        if (卡片项 := _解析入口JSON(入口文件, 来源标签, "drive")) and 状态.添加来源卡片(卡片项):
            卡片列表.append(卡片项)
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


def _扫描ADB文件夹(
    ADB路径: str,
    序列号: str,
    远端路径: str,
    根文件夹: str,
    来源标签: str,
) -> list[视频卡片]:
    r"""
    递归搜索 ADB 设备目录中的 video.m4s / audio.m4s 文件对
    逻辑参考 biliandout ScanWorker._find_m4s_adb：
      - 当前目录同时包含两个文件 → 命中，解析元数据
      - 否则递归子目录
    :param: adb: adb 路径
    :param: serial: 设备序列号
    :param: remote_path: 当前远端目录
    :param: root_folder: 根文件夹名（用于标题回退）
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    卡片列表: list[视频卡片] = []
    if 状态._扫描取消.is_set():
        return 卡片列表
    try:
        执行结果: 子进程.CompletedProcess = _执行ADB(
            ADB路径,
            序列号,
            "shell",
            f"ls -1a '{远端路径}'",
            超时秒数=10,
        )
        if 执行结果.returncode != 0:
            return 卡片列表
        条目列表: list[str] = _解析列表输出(执行结果.stdout)
        if "video.m4s" in 条目列表 and "audio.m4s" in 条目列表:
            if 卡片 := _制作ADB卡片(ADB路径, 序列号, 远端路径, 根文件夹, 来源标签):
                卡片列表.append(卡片)
        else:
            for 条目 in 条目列表:
                if 条目 in (".", ".."):
                    continue
                卡片列表.extend(
                    _扫描ADB文件夹(
                        ADB路径,
                        序列号,
                        f"{远端路径}/{条目}",
                        根文件夹,
                        来源标签,
                    )
                )
    except Exception:
        pass
    return 卡片列表


def _遍历ADB包(包名: str) -> list[tuple[str, str]]:
    请求包名: str = 包名.strip()
    if not 请求包名:
        return list(_哔哩包列表)
    if 请求包名 in _哔哩包名表:
        return [(请求包名, _哔哩包名表[请求包名])]
    状态.记录日志("warn", f"未知 B 站包名: {请求包名}")
    return []


def _拉取ADB封面(ADB路径: str, 序列号: str, 远端目录: str, 标识符: str) -> str:
    r"""
    从 ADB 设备拉取 cover.jpg 到本地缓存目录，命中缓存直接返回
    参考 biliandout ScanWorker._pull_cover_adb
    :param: adb: adb 路径
    :param: serial: 设备序列号
    :param: remote_dir: 远端目录（向上搜索起点）
    :param: identifier: 唯一标识（用于哈希命名）
    :return: str: 本地缓存路径, 失败返回空串
    """
    安全编号: str = 哈希.md5(f"{远端目录}_{标识符}".encode()).hexdigest()
    for 扩展名 in ("jpg", "jpeg", "png"):
        缓存文件: 路径 = _封面缓存目录 / f"{安全编号}.{扩展名}"
        if 缓存文件.exists() and 缓存文件.stat().st_size > 0:
            return str(缓存文件)

    当前目录: str = 远端目录
    for _ in range(4):
        for 扩展名 in ("jpg", "jpeg", "png"):
            目标文件: 路径 = _封面缓存目录 / f"{安全编号}.{扩展名}"
            try:
                执行结果: 子进程.CompletedProcess = _执行ADB(
                    ADB路径,
                    序列号,
                    "pull",
                    f"{当前目录}/cover.{扩展名}",
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


def _制作ADB卡片(
    ADB路径: str,
    序列号: str,
    远端路径: str,
    根文件夹: str,
    来源标签: str,
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
    AV号: str = ""
    UP主名称: str = ""

    # 尝试从父目录拉取 entry.json
    远端父目录: str = 远端路径.rsplit("/", 1)[0] if "/" in 远端路径 else 远端路径
    # 针对新版 B 站 Android 缓存进行路径智能上移
    路径片段: list[str] = 远端路径.split("/")
    if "download" in 路径片段:
        索引 = 路径片段.index("download")
        深度 = len(路径片段) - 1 - 索引
        if 深度 == 3:
            远端父目录 = "/".join(路径片段[:-2])
        elif 深度 == 2:
            远端父目录 = "/".join(路径片段[:-1])
    临时路径: str = ""
    try:
        with 临时文件.NamedTemporaryFile(suffix=".json", delete=False) as 临时对象:
            临时路径 = 临时对象.name
        拉取结果: 子进程.CompletedProcess = _执行ADB(
            ADB路径,
            序列号,
            "pull",
            f"{远端父目录}/entry.json",
            临时路径,
            超时秒数=10,
        )
        if 拉取结果.returncode == 0 and 路径(临时路径).exists():
            数据: dict = 数据交换.loads(路径(临时路径).read_text(encoding="utf-8"))
            标题 = 数据.get("title", 根文件夹) or 根文件夹
            BV号 = 数据.get("bvid", "") or ""
            AV号 = str(数据.get("avid", ""))
            UP主名称 = 数据.get("owner_name", "")
            清晰度 = 数据.get("quality_pithy_description", "")
            页面数据: dict = 数据.get("page_data", {})
            宽度, 高度 = 页面数据.get("width", 0), 页面数据.get("height", 0)
            if 宽度 and 高度:
                分辨率 = f"{宽度}×{高度}"
            字节数 = 数据.get("total_bytes", 0)
    except Exception:
        pass
    finally:
        if 临时路径:
            路径(临时路径).unlink(missing_ok=True)

    # 尝试拉取 index.json 解析分辨率/帧率（与 m4s 同目录）
    if not 分辨率 or not 帧率:
        索引临时路径: str = ""
        try:
            with 临时文件.NamedTemporaryFile(suffix=".json", delete=False) as 临时对象:
                索引临时路径 = 临时对象.name
            索引拉取结果: 子进程.CompletedProcess = _执行ADB(
                ADB路径,
                序列号,
                "pull",
                f"{远端路径}/index.json",
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

    # 拉取封面（向上 4 层查找）
    封面路径: str = _拉取ADB封面(ADB路径, 序列号, 远端父目录, 根文件夹)

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
        清晰度=清晰度,
        分辨率=分辨率,
        字节数=字节数,
        文件夹名=根文件夹,
        来源标签=来源标签,
        来源类型="adb",
        设备序列号=序列号,
        视频路径=f"{远端路径}/video.m4s",
        音频路径=f"{远端路径}/audio.m4s",
        封面路径=封面路径,
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

    for 包名项, 包显示名 in _遍历ADB包(包名):
        远端根目录: str = f"/sdcard/Android/data/{包名项}/download"
        try:
            执行结果: 子进程.CompletedProcess = _执行ADB(
                ADB路径,
                序列号,
                "shell",
                f"ls -1a '{远端根目录}'",
                超时秒数=15,
            )
            if 执行结果.returncode != 0:
                continue
            文件夹列表: list[str] = _解析列表输出(执行结果.stdout)
            总数: int = len(文件夹列表)
            for 序号, 文件夹名 in enumerate(文件夹列表):
                if 状态._扫描取消.is_set():
                    break
                while 状态._扫描暂停.is_set() and not 状态._扫描取消.is_set():
                    时间.sleep(0.2)
                for 卡片项 in _扫描ADB文件夹(
                    ADB路径,
                    序列号,
                    f"{远端根目录}/{文件夹名}",
                    文件夹名,
                    来源标签,
                ):
                    if 状态.添加来源卡片(卡片项):
                        卡片列表.append(卡片项)
                if 总数:
                    with 状态.锁:
                        状态.扫描进度 = (序号 + 1) / 总数
        except Exception as e:
            状态.记录日志("warn", f"扫描 {包显示名} 失败: {e}")

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
    try:
        状态.记录日志("info", f"开始扫描: {标签}")
        with 状态.锁:
            状态.扫描状态 = "scanning"
            状态.扫描进度 = 0.0

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
            with 状态.锁:
                待补全列表: list[视频卡片] = [卡片项 for 卡片项 in 状态.来源卡片列表 if not (卡片项.标题 and 卡片项.UP主名称)]
            for 卡片项 in 待补全列表:
                if 状态._扫描取消.is_set():
                    break
                _爬虫补全(卡片项)

        with 状态.锁:
            状态.扫描状态 = "idle"
            状态.扫描进度 = 1.0

        if 状态._扫描取消.is_set():
            状态.记录日志("warn", "扫描已取消")
        else:
            状态.记录日志("success", f"扫描完成: 发现 {len(发现列表)} 个视频")
    except Exception as e:
        状态.记录日志("error", f"扫描异常: {e}")
        with 状态.锁:
            状态.扫描状态 = "idle"
    finally:
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


def _本地合并(卡片: 视频卡片, 输出路径: str) -> None:
    r"""
    本地文件合并，自动区分两种命名方案：

    - Android 标准命名（video.m4s / audio.m4s）：
      调用 biliffm4s.combine(parent_dir, output)
      由 biliffm4s 在父目录中递归查找两个标准命名文件后合并

    - PC codec-id 命名（如 64-1-xxx.m4s / 30280-1-xxx.m4s）：
      调用 biliffm4s.convert(video_path, audio_path, output)
      显式指定两个文件路径合并

    :param: card: 视频卡片
    :param: output: 输出 mp4 路径
    :raise: FileNotFoundError: 文件不存在
    :raise: RuntimeError: biliffm4s 合并失败
    """
    视频文件: str = 卡片.视频路径
    音频文件: str = 卡片.音频路径

    if not 视频文件 or not 路径(视频文件).exists():
        raise FileNotFoundError(f"视频文件不存在: {视频文件}")

    if 路径(视频文件).name.lower() == "video.m4s":
        # Android 标准命名 → combine(父目录, 输出)
        结果: bool = _缓存合并库.combine(str(路径(视频文件).parent), 输出路径)
    else:
        # PC codec-id 命名 → convert(视频, 音频, 输出)
        if not 音频文件 or not 路径(音频文件).exists():
            raise FileNotFoundError(f"音频文件不存在: {音频文件}")
        结果 = _缓存合并库.convert(视频文件, 音频文件, 输出路径)

    if not 结果:
        raise RuntimeError("biliffm4s 合并失败")


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
                raise RuntimeError(f"ADB 拉取{名称}失败: {拉取结果.stderr.strip()[:120]}")

        # 拉取后标准命名，直接使用 combine
        结果: bool = _缓存合并库.combine(临时目录, 输出路径)
        if not 结果:
            raise RuntimeError("biliffm4s 合并失败")


def _导出单个(卡片: 视频卡片, 输出目录: 路径) -> None:
    r"""
    导出单个视频（自动区分本地与 ADB 来源）
    :param: card: 视频卡片
    :param: output_dir: 输出目录
    """
    if not _有合并库:
        raise RuntimeError("biliffm4s 未安装")

    文件名文本: str = _构建文件名(卡片)
    if not 文件名文本:
        raise RuntimeError("标题不完整且策略为跳过")

    输出路径: 路径 = 输出目录 / 文件名文本
    计数器: int = 1
    while 输出路径.exists():
        输出路径 = 输出目录 / f"{输出路径.stem}_{计数器}.mp4"
        计数器 += 1

    if 卡片.来源类型 == "adb":
        _导出单个ADB(卡片, str(输出路径))
    else:
        _本地合并(卡片, str(输出路径))
    卡片.输出路径 = str(输出路径)


def _导出线程函数(卡片编号列表: list[str]) -> None:
    r"""
    导出线程入口函数
    :param: card_ids: 待导出的卡片 ID 列表
    """
    输出目录: 路径 = 工具.取导出路径() / 工具.取设置("localout", "folder")
    输出目录.mkdir(parents=True, exist_ok=True)

    并发数: int = max(1, min(int(工具.取设置("localout", "ffmpeg_concurrent") or "3"), 32))

    with 状态.锁:
        目标列表: list[视频卡片] = [卡片项 for 卡片项 in 状态.任务卡片列表 if 卡片项.编号 in 卡片编号列表]
        状态.导出总数 = len(目标列表)
        状态.导出完成数 = 0
        状态.导出进度 = 0.0
        状态.导出状态 = "exporting"

    状态.记录日志("info", f"开始导出 {len(目标列表)} 个视频 (并发 {并发数})")

    def _导出一个(卡片: 视频卡片) -> None:
        if 状态._导出取消.is_set():
            return
        with 状态.锁:
            卡片.状态名 = "exporting"
        状态.记录日志("info", f"导出中: {卡片.标题 or 卡片.文件夹名}")
        try:
            _导出单个(卡片, 输出目录)
            with 状态.锁:
                卡片.状态名 = "success"
                状态.任务卡片列表 = [卡片项 for 卡片项 in 状态.任务卡片列表 if 卡片项.编号 != 卡片.编号]
                状态.完成卡片列表.append(卡片)
                状态.导出完成数 += 1
                状态.导出进度 = 状态.导出完成数 / 状态.导出总数 if 状态.导出总数 else 1
            状态.记录日志("success", f"导出完成: {卡片.标题 or 卡片.文件夹名}")
        except Exception as e:
            with 状态.锁:
                卡片.状态名 = "failed"
                卡片.错误 = str(e)
                状态.导出完成数 += 1
                状态.导出进度 = 状态.导出完成数 / 状态.导出总数 if 状态.导出总数 else 1
            状态.记录日志("error", f"导出失败: {卡片.标题 or 卡片.文件夹名} — {e}")

    with 线程池执行器(max_workers=并发数) as 卡片池:
        任务映射: dict = {卡片池.submit(_导出一个, 卡片项): 卡片项 for 卡片项 in 目标列表}
        for _ in 逐个完成(任务映射):
            if 状态._导出取消.is_set():
                break

    with 状态.锁:
        状态.导出状态 = "idle"
    if 状态._导出取消.is_set():
        状态.记录日志("warn", "导出已取消")
    else:
        状态.记录日志("success", f"全部导出任务结束 (成功 {状态.导出完成数}/{状态.导出总数})")
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
    有合并库: bool = _有合并库
    有网络请求: bool = _有网络请求

    return {
        "adb": {
            "available": ADB路径值 is not None,
            "path": ADB路径值 or "",
            "hint": "请安装 ADB 并添加到 PATH，或放入 mybiout/bin/ 目录" if not ADB路径值 else "",
        },
        "biliffm4s": {
            "available": 有合并库,
            "hint": "请运行: pip install biliffm4s" if not 有合并库 else "",
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
    if not _有合并库:
        警告列表.append("biliffm4s 未安装，导出功能将不可用")

    ADB路径值: str | None = _寻找ADB()
    if not ADB路径值:
        警告列表.append("ADB 未找到，无法扫描 Android 设备（USB调试模式）")

    # PC 桌面端缓存
    电脑缓存路径: str = 工具.取设置("localout", "bilibili_pc_cache_path").strip()
    if 电脑缓存路径:
        可选路径: bool = 工具.取设置("localout", "bilibili_pc_cache_optional_when_installed") == "true"
        if not (可选路径 and not 路径(电脑缓存路径).is_dir()):
            来源列表.append(
                {
                    "id": "pc_cache",
                    "label": "哔哩哔哩桌面端缓存",
                    "icon": "💻",
                    "type": "pc",
                    "path": 电脑缓存路径,
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
        for 包名项, 名称 in _哔哩包列表:
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

    with 状态.锁:
        if 状态.扫描状态 == "scanning":
            return {"ok": False, "error": "已有扫描在进行中"}

    if 来源类型 not in {"pc", "drive", "adb", "local"}:
        return {"ok": False, "error": f"未知扫描源类型: {来源类型}"}

    if 来源类型 == "adb":
        if not 序列号:
            return {"ok": False, "error": "ADB 设备序列号为空"}
        if 包名 and 包名 not in _哔哩包名表:
            return {"ok": False, "error": f"未知 B 站包名: {包名}"}
    else:
        if not 路径文本 or not 路径(路径文本).is_dir():
            return {"ok": False, "error": f"路径不存在: {路径文本 or '(空)'}"}

    状态._扫描取消.clear()
    状态._扫描暂停.clear()
    线程对象: 线程.Thread = 线程.Thread(
        target=_扫描线程函数,
        args=(来源类型, 路径文本, 标签 or 路径文本 or 来源类型, 序列号, 包名),
        daemon=True,
    )
    with 状态.锁:
        状态._扫描线程 = 线程对象
    线程对象.start()
    return {"ok": True}


def 暂停扫描() -> None:
    状态._扫描暂停.set()
    with 状态.锁:
        if 状态.扫描状态 == "scanning":
            状态.扫描状态 = "paused"
    状态.记录日志("info", "扫描已暂停")


def 继续扫描() -> None:
    状态._扫描暂停.clear()
    with 状态.锁:
        if 状态.扫描状态 == "paused":
            状态.扫描状态 = "scanning"
    状态.记录日志("info", "扫描已继续")


def 取消扫描() -> None:
    状态._扫描取消.set()
    状态._扫描暂停.clear()
    with 状态.锁:
        状态.扫描状态 = "idle"


def 加入任务(卡片编号列表: list[str]) -> dict:
    r"""
    将源卡片添加到任务栏
    :param: card_ids: 源卡片 ID 列表
    :return: dict
    """
    添加数量: int = 0
    with 状态.锁:
        已有集合: set[tuple[str, str]] = {(卡片项.视频路径, 卡片项.音频路径) for 卡片项 in 状态.任务卡片列表}
        for 来源编号 in 卡片编号列表:
            for 来源卡片 in 状态.来源卡片列表:
                if 来源卡片.编号 == 来源编号:
                    键: tuple[str, str] = (来源卡片.视频路径, 来源卡片.音频路径)
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
        if 状态.导出状态 == "exporting":
            return {"ok": False, "error": "导出正在进行中"}
    if not 卡片编号列表:
        with 状态.锁:
            卡片编号列表 = [卡片项.编号 for 卡片项 in 状态.任务卡片列表 if 卡片项.状态名 == "queued"]
    if not 卡片编号列表:
        return {"ok": False, "error": "没有可导出的任务"}

    状态._导出取消.clear()
    线程对象: 线程.Thread = 线程.Thread(
        target=_导出线程函数,
        args=(卡片编号列表,),
        daemon=True,
    )
    with 状态.锁:
        状态._导出线程 = 线程对象
    线程对象.start()
    return {"ok": True}


def 取消导出() -> None:
    状态._导出取消.set()
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
