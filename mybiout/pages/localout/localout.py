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

    _HAS_HTTPX: bool = True
except Exception:
    网络请求 = None
    _HAS_HTTPX: bool = False

try:
    from biliffm4s import biliffm4s as _ffm4s

    _HAS_FFM4S: bool = True
except Exception:
    _ffm4s = None
    _HAS_FFM4S: bool = False

_BILI_PACKAGES: list[tuple[str, str]] = [
    ("tv.danmaku.bili", "哔哩哔哩"),
    ("com.bilibili.app.blue", "哔哩哔哩概念版"),
    ("com.bilibili.app.in", "哔哩哔哩国际版"),
]
_BILI_PACKAGE_NAMES: dict[str, str] = dict(_BILI_PACKAGES)

_CRAWLER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}

_QN_MAP: dict[int, str] = {
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

_AUDIO_CODEC_THRESHOLD: int = 30200

_POPEN_EXTRA: dict = {}
if 系统信息.platform == "win32":
    _POPEN_EXTRA["creationflags"] = 0x08000000

_COVER_CACHE_DIR: 路径 = 路径(临时文件.gettempdir()) / "mybiout_covers"
_COVER_CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ===== ADB 工具 =====


def _find_adb() -> str | None:
    r"""
    查找 adb 可执行文件路径（参考 biliandout DeviceScanner.find_adb）
    :return: str | None: 路径, 未找到返回 None
    """
    bin_name: str = "adb.exe" if 系统信息.platform == "win32" else "adb"
    if 文件工具.which(bin_name) or 文件工具.which("adb"):
        return bin_name
    if 系统信息.platform == "win32":
        for candidate in (
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
            if candidate.exists():
                return str(candidate)
    return None


def _adb_run(adb: str, serial: str, *args: str, timeout: float = 10) -> 子进程.CompletedProcess:
    r"""
    执行 adb [-s serial] <args> 命令
    :param: adb: adb 可执行文件路径
    :param: serial: 设备序列号（为空时省略 -s 参数）
    :param: args: 后续命令参数
    :param: timeout: 超时秒数
    :return: subprocess.CompletedProcess
    """
    cmd: list[str] = [adb]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    return 子进程.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        **_POPEN_EXTRA,
    )


def _get_adb_devices() -> list[tuple[str, str]]:
    r"""
    获取已通过 ADB 连接且授权的设备列表（参考 biliandout DeviceScanner.get_adb_devices）
    :return: list[tuple[str, str]]: [(序列号, 显示名称), ...]
    """
    devices: list[tuple[str, str]] = []
    adb: str | None = _find_adb()
    if not adb:
        return devices
    try:
        result: 子进程.CompletedProcess = _adb_run(adb, "", "devices", "-l", timeout=8)
        if result.returncode != 0:
            return devices
        for line in result.stdout.strip().splitlines()[1:]:
            if not line.strip():
                continue
            parts: list[str] = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                serial: str = parts[0]
                model: str = "Android设备"
                for part in parts[2:]:
                    if part.startswith("model:"):
                        model = part.split(":", 1)[1].replace("_", " ")
                        break
                devices.append((serial, f"{model} ({serial})"))
    except Exception:
        pass
    return devices


# ===== 通用工具 =====


def _生成编号() -> str:
    return 唯一编号.uuid4().hex[:12]


def _短时间() -> str:
    return 日期时间.now().strftime("%H:%M:%S")


def _完整时间() -> str:
    return 日期时间.now().strftime("%Y-%m-%d %H:%M:%S")


def _取卷标(letter: str) -> str:
    r"""
    获取驱动器卷标
    :param: letter: 单个大写盘符字母
    :return: str: 卷标名称
    """
    if 系统信息.platform == "win32":
        buf: 系统接口.Array = 系统接口.create_unicode_buffer(261)
        try:
            ret: int = 系统接口.windll.kernel32.GetVolumeInformationW(
                f"{letter}:\\",
                buf,
                261,
                None,
                None,
                None,
                None,
                0,
            )
            if ret and buf.value:
                return buf.value
        except Exception:
            pass
    return f"存储设备 ({letter}:)"


def _清理文件名(name: str) -> str:
    name = 正则.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")
    return name[:200] if name else "untitled"


def _兆字节(b: int | float) -> float:
    return round(b / 1048576, 1) if b else 0


# ===== 数据模型 =====


@数据类(slots=True)
class 视频卡片:
    r"""
    视频缓存卡片数据模型, 表示一个被扫描到的缓存视频
    """

    id: str = 字段(default_factory=_生成编号)
    title: str = ""
    bvid: str = ""
    avid: str = ""
    up_name: str = ""
    group_title: str = ""
    part: int = 1
    quality: str = ""
    resolution: str = ""
    size_bytes: int = 0
    publish_time: str = ""
    folder_name: str = ""
    source_label: str = ""
    source_type: str = ""
    device_serial: str = ""
    video_path: str = ""
    audio_path: str = ""
    cover_path: str = ""
    output_path: str = ""
    status: str = "queued"
    error: str = ""

    def __post_init__(self) -> None:
        self.avid = str(self.avid)
        self.part = int(self.part)
        self.size_bytes = int(self.size_bytes)

    def to_dict(self) -> dict:
        alive: bool = True
        if self.source_type in ("local", "pc", "drive") and self.video_path:
            alive = 路径(self.video_path).exists()
        return {
            "id": self.id,
            "title": self.title,
            "bvid": self.bvid,
            "avid": self.avid,
            "up_name": self.up_name,
            "group_title": self.group_title,
            "part": self.part,
            "quality": self.quality,
            "resolution": self.resolution,
            "size_bytes": self.size_bytes,
            "size_mb": _兆字节(self.size_bytes),
            "publish_time": self.publish_time,
            "folder_name": self.folder_name,
            "source_label": self.source_label,
            "source_type": self.source_type,
            "cover_url": f"/api/localout/cover/{self.id}" if self.cover_path else "",
            "video_path": self.video_path,
            "output_path": self.output_path,
            "path_display": self.output_path or str(路径(self.video_path).parent if self.video_path else ""),
            "alive": alive,
            "status": self.status,
            "error": self.error,
        }

    def clone(self) -> 视频卡片:
        return 替换数据(self, id=_生成编号(), status="queued", error="", output_path="")


# ===== 全局状态 =====


class _本地状态:
    r"""
    LocalOut 全局运行状态管理
    """

    def __init__(self) -> None:
        self.lock: 线程.RLock = 线程.RLock()
        self.source_cards: list[视频卡片] = []
        self.task_cards: list[视频卡片] = []
        self.completed_cards: list[视频卡片] = []
        self.logs: list[dict] = []
        self.scan_status: str = "idle"
        self.scan_progress: float = 0.0
        self.export_status: str = "idle"
        self.export_progress: float = 0.0
        self.export_total: int = 0
        self.export_done: int = 0
        self._scan_thread: 线程.Thread | None = None
        self._scan_cancel: 线程.Event = 线程.Event()
        self._scan_pause: 线程.Event = 线程.Event()
        self._export_thread: 线程.Thread | None = None
        self._export_cancel: 线程.Event = 线程.Event()
        self._known_keys: set[str] = set()
        self._available_keys: set[str] = set()
        self._last_available_refresh: float = 0.0

    def log(self, level: str, msg: str) -> None:
        with self.lock:
            self.logs.append({"time": _短时间(), "level": level, "msg": msg})
            if len(self.logs) > 500:
                self.logs = self.logs[-300:]

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "source_cards": [c.to_dict() for c in self.source_cards],
                "task_cards": [c.to_dict() for c in self.task_cards],
                "completed_cards": [c.to_dict() for c in self.completed_cards],
                "logs": list(self.logs),
                "available_keys": sorted(self._available_keys),
                "scan_status": self.scan_status,
                "scan_progress": round(self.scan_progress, 3),
                "export_status": self.export_status,
                "export_progress": round(self.export_progress, 3),
                "export_total": self.export_total,
                "export_done": self.export_done,
            }

    def _dedup_key(self, c: 视频卡片) -> str:
        # 含 device_serial 避免不同 ADB 设备的相同路径发生碰撞
        return f"{c.source_type}|{c.device_serial}|{c.video_path}|{c.audio_path}"

    def add_source_card(self, c: 视频卡片) -> bool:
        k: str = self._dedup_key(c)
        with self.lock:
            if k in self._known_keys:
                return False
            self._known_keys.add(k)
            self.source_cards.append(c)
            return True


状态: _本地状态 = _本地状态()


# ===== 解析 / 查找函数 =====


def _解析入口JSON(
    path: 路径,
    source_label: str,
    source_type: str,
    serial: str = "",
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
        data: dict = 数据交换.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    page_data: dict = data.get("page_data") or {}
    w: int = page_data.get("width", 0)
    h: int = page_data.get("height", 0)
    type_tag: str = str(data.get("type_tag", ""))
    parent_dir: 路径 = path.parent

    video_path: str = ""
    audio_path: str = ""

    # 优先按 type_tag（画质数字子目录）查找
    if type_tag and (quality_dir := parent_dir / type_tag).is_dir():
        if (vp := quality_dir / "video.m4s").exists():
            video_path = str(vp)
        if (ap := quality_dir / "audio.m4s").exists():
            audio_path = str(ap)

    # 降级：遍历子目录查找
    if not video_path:
        for sub in parent_dir.iterdir():
            if sub.is_dir():
                if (vp := sub / "video.m4s").exists():
                    video_path = str(vp)
                if (ap := sub / "audio.m4s").exists():
                    audio_path = str(ap)
                if video_path:
                    break

    if not video_path:
        return None

    return 视频卡片(
        title=data.get("title", ""),
        bvid=data.get("bvid", "") or "",
        avid=str(data.get("avid", "")),
        up_name=data.get("owner_name", ""),
        part=page_data.get("page", 1),
        quality=data.get("quality_pithy_description", ""),
        resolution=f"{w}×{h}" if w and h else "",
        size_bytes=data.get("total_bytes", 0),
        folder_name=parent_dir.name,
        source_label=source_label,
        source_type=source_type,
        device_serial=serial,
        video_path=video_path,
        audio_path=audio_path,
        cover_path=_向上寻找封面(parent_dir),
    )


def _递归寻找M4S(root: 路径, source_label: str, source_type: str) -> list[视频卡片]:
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
    cards: list[视频卡片] = []
    vp: 路径 = root / "video.m4s"
    ap: 路径 = root / "audio.m4s"
    if vp.exists() and ap.exists():
        if card := _从M4S目录制卡(root, source_label, source_type):
            cards.append(card)
    else:
        try:
            for sub in root.iterdir():
                if sub.is_dir():
                    cards.extend(_递归寻找M4S(sub, source_label, source_type))
        except PermissionError:
            pass
    return cards


def _解析列表输出(stdout: str) -> list[str]:
    r"""
    解析 adb shell ls 输出，过滤空行、错误前缀、控制字符（处理彩色输出）
    参考 biliandout ScanWorker 经验：某些 Android ROM 默认 ls 输出带 ANSI 颜色
    :param: stdout: adb shell ls 原始输出
    :return: list[str]: 清理后的条目名列表
    """
    out: list[str] = []
    ansi_re: 正则.Pattern[str] = 正则.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
    for line in stdout.splitlines():
        cleaned: str = ansi_re.sub("", line).strip()
        if not cleaned:
            continue
        if cleaned.startswith("ls:"):
            continue
        if cleaned in (".", ".."):
            continue
        out.append(cleaned)
    return out


def _寻找电脑M4S(cache_dir: 路径) -> tuple[str, str]:
    r"""
    在 PC 缓存目录中查找 video 和 audio m4s 文件（通过 codec-id 区分）
    :param: cache_dir: 缓存子目录
    :return: tuple[str, str]: (视频路径, 音频路径)
    """
    video: str = ""
    audio: str = ""
    for f in cache_dir.iterdir():
        if f.suffix == ".m4s" and f.is_file():
            parts_: list[str] = f.stem.split("-")
            if len(parts_) >= 3:
                try:
                    codec_id: int = int(parts_[-1])
                    if codec_id >= _AUDIO_CODEC_THRESHOLD:
                        audio = str(f)
                    else:
                        video = str(f)
                except ValueError:
                    if not video:
                        video = str(f)
            elif not video:
                video = str(f)
    return video, audio


def _解析视频信息JSON(path: 路径, source_label: str) -> 视频卡片 | None:
    r"""
    解析 PC 缓存 videoInfo.json 文件
    :param: path: videoInfo.json 路径
    :param: source_label: 来源标签
    :return: VideoCard | None
    """
    try:
        data: dict = 数据交换.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    qn: int = data.get("qn", 0)
    pubdate: int = data.get("pubdate", 0)
    publish_time: str = ""
    if pubdate:
        with 忽略异常(Exception):
            publish_time = 日期时间.fromtimestamp(pubdate).strftime("%Y-%m-%d %H:%M")

    cache_dir: 路径 = path.parent
    video_path, audio_path = _寻找电脑M4S(cache_dir)
    if not video_path:
        return None

    return 视频卡片(
        title=data.get("title", "") or data.get("groupTitle", ""),
        bvid=data.get("bvid", "") or "",
        avid=str(data.get("aid", "") or ""),
        up_name=data.get("uname", ""),
        group_title=data.get("groupTitle", "") or "",
        part=data.get("p", 1),
        quality=_QN_MAP.get(qn, str(qn) if qn else ""),
        size_bytes=data.get("totalSize", 0),
        publish_time=publish_time,
        folder_name=cache_dir.name,
        source_label=source_label,
        source_type="pc",
        video_path=video_path,
        audio_path=audio_path,
        cover_path=_向上寻找封面(cache_dir),
    )


def _解析索引JSON(path: 路径) -> tuple[str, str, int]:
    r"""
    解析 Android 新版 index.json (与 video.m4s/audio.m4s 同目录)
    :param: path: index.json 路径
    :return: (分辨率字符串, 帧率字符串, 视频码率)
    """
    try:
        data: dict = 数据交换.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "", "", 0
    video_list: list = data.get("video", []) or []
    if not video_list:
        return "", "", 0
    v: dict = video_list[0]
    w: int = int(v.get("width", 0) or 0)
    h: int = int(v.get("height", 0) or 0)
    resolution: str = f"{w}×{h}" if w and h else ""
    frame_rate: str = ""
    if fps := v.get("frame_rate"):
        try:
            f: float = float(fps)
            frame_rate = f"{f:.0f}fps" if f == int(f) else f"{f:.1f}fps"
        except ValueError, TypeError:
            pass
    return resolution, frame_rate, int(v.get("bandwidth", 0) or 0)


def _向上寻找封面(start: 路径, max_depth: int = 3) -> str:
    r"""
    从 start 起向上查找 cover.jpg / cover.jpeg / cover.png (含 start 自身)
    :param: start: 起始目录
    :param: max_depth: 最多上溯层数
    :return: str: cover 路径, 找不到返回空串
    """
    cur: 路径 = start
    for _ in range(max_depth + 1):
        for name in ("cover.jpg", "cover.jpeg", "cover.png"):
            cand: 路径 = cur / name
            if cand.exists():
                return str(cand)
        if cur.parent == cur:
            break
        cur = cur.parent
    return ""


def _从M4S目录制卡(m4s_dir: 路径, source_label: str, source_type: str) -> 视频卡片 | None:
    r"""
    针对 "目录中含 video.m4s + audio.m4s" 的通用情况构造 VideoCard
    自动尝试解析同目录下 index.json 与上溯查找封面
    :param: m4s_dir: 包含两个 m4s 文件的目录
    :param: source_label: 来源标签
    :param: source_type: 来源类型
    :return: VideoCard | None
    """
    vp: 路径 = m4s_dir / "video.m4s"
    ap: 路径 = m4s_dir / "audio.m4s"
    if not (vp.exists() and ap.exists()):
        return None

    size: int = 0
    with 忽略异常(OSError):
        size = vp.stat().st_size + ap.stat().st_size

    resolution: str = ""
    frame_rate: str = ""
    if (idx := m4s_dir / "index.json").exists():
        resolution, frame_rate, _ = _解析索引JSON(idx)

    quality: str = ""
    with 忽略异常(ValueError):
        quality = _QN_MAP.get(int(m4s_dir.name), "")
    if frame_rate:
        quality = f"{quality} {frame_rate}".strip()

    folder: 路径 = m4s_dir.parent if m4s_dir.parent != m4s_dir else m4s_dir
    return 视频卡片(
        folder_name=folder.name or m4s_dir.name,
        source_label=source_label,
        source_type=source_type,
        video_path=str(vp),
        audio_path=str(ap),
        size_bytes=size,
        resolution=resolution,
        quality=quality,
        cover_path=_向上寻找封面(m4s_dir.parent),
    )


def _爬虫补全(card: 视频卡片) -> None:
    r"""
    若设置启用爬虫降级, 当卡片缺失关键元数据(title/up)时, 尝试用 BV 号补全
    :param: card: 待补全卡片 (就地修改)
    """
    timeout: float | None = 工具.取爬虫兜底超时()
    if timeout is None or not _HAS_HTTPX:
        return
    if card.title and card.up_name:
        return
    if not card.bvid:
        if m := 正则.search(r"(BV[\w]{10,})", card.folder_name or ""):
            card.bvid = m.group(1)
        else:
            return
    try:
        with 网络请求.Client(headers=_CRAWLER_HEADERS, timeout=timeout) as c:
            r = c.get(
                "https://api.bilibili.com/x/web-interface/view",
                params={"bvid": card.bvid},
            )
            data: dict = r.json()
        if data.get("code") != 0:
            return
        info: dict = data.get("data", {})
        if not card.title:
            card.title = info.get("title", "")
        if not card.up_name:
            card.up_name = info.get("owner", {}).get("name", "")
        if not card.publish_time and (pubdate := info.get("pubdate")):
            with 忽略异常(Exception):
                card.publish_time = 日期时间.fromtimestamp(pubdate).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass


# ===== 扫描函数 =====


def _扫描本地目录(root: 路径, source_label: str) -> list[视频卡片]:
    r"""
    扫描本地目录：优先解析 entry.json / videoInfo.json，
    若均无则递归查找任意 video.m4s / audio.m4s 对
    :param: root: 根目录
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    cards: list[视频卡片] = []
    entry_files: list[路径] = list(root.rglob("entry.json"))
    vi_files: list[路径] = list(root.rglob("videoInfo.json"))
    total: int = len(entry_files) + len(vi_files)

    for i, ef in enumerate(entry_files):
        if 状态._scan_cancel.is_set():
            break
        while 状态._scan_pause.is_set() and not 状态._scan_cancel.is_set():
            时间.sleep(0.2)
        if (c := _解析入口JSON(ef, source_label, "local")) and 状态.add_source_card(c):
            cards.append(c)
        if total:
            with 状态.lock:
                状态.scan_progress = (i + 1) / total

    for i, vf in enumerate(vi_files):
        if 状态._scan_cancel.is_set():
            break
        while 状态._scan_pause.is_set() and not 状态._scan_cancel.is_set():
            时间.sleep(0.2)
        if (c := _解析视频信息JSON(vf, source_label)) and 状态.add_source_card(c):
            cards.append(c)
        if total:
            with 状态.lock:
                状态.scan_progress = (len(entry_files) + i + 1) / total

    # 通用回退：当目录中没有任何 JSON 元数据时，递归查找 m4s 对
    if not cards and not entry_files and not vi_files:
        fallback: list[视频卡片] = _递归寻找M4S(root, source_label, "local")
        for c in fallback:
            if 状态.add_source_card(c):
                cards.append(c)

    return cards


def _扫描电脑缓存(root: 路径, source_label: str) -> list[视频卡片]:
    r"""
    扫描 PC 桌面端缓存目录
    :param: root: 缓存根目录
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    cards: list[视频卡片] = []
    if not root.is_dir():
        状态.log("error", f"PC 缓存路径不存在: {root}")
        return cards

    subdirs: list[路径] = [d for d in root.iterdir() if d.is_dir()]
    total: int = len(subdirs)

    for i, sd in enumerate(subdirs):
        if 状态._scan_cancel.is_set():
            break
        while 状态._scan_pause.is_set() and not 状态._scan_cancel.is_set():
            时间.sleep(0.2)

        if (vf := sd / "videoInfo.json").exists():
            if (c := _解析视频信息JSON(vf, source_label)) and 状态.add_source_card(c):
                cards.append(c)
        else:
            video, audio = _寻找电脑M4S(sd)
            if video:
                c = 视频卡片(
                    folder_name=sd.name,
                    source_label=source_label,
                    source_type="pc",
                    video_path=video,
                    audio_path=audio,
                    cover_path=_向上寻找封面(路径(video).parent),
                )
                if 状态.add_source_card(c):
                    cards.append(c)
            else:
                for nested in _递归寻找M4S(sd, source_label, "pc"):
                    if 状态.add_source_card(nested):
                        cards.append(nested)

        if total:
            with 状态.lock:
                状态.scan_progress = (i + 1) / total

    return cards


def _扫描磁盘(root: 路径, source_label: str) -> list[视频卡片]:
    r"""
    扫描挂载为本地驱动器的 Android 设备缓存
    :param: root: 下载目录（如 E:/Android/data/tv.danmaku.bili/download）
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    cards: list[视频卡片] = []
    if not root.is_dir():
        状态.log("error", f"驱动器缓存路径不存在: {root}")
        return cards

    entry_files: list[路径] = list(root.rglob("entry.json"))
    total: int = len(entry_files)

    for i, ef in enumerate(entry_files):
        if 状态._scan_cancel.is_set():
            break
        while 状态._scan_pause.is_set() and not 状态._scan_cancel.is_set():
            时间.sleep(0.2)
        if (c := _解析入口JSON(ef, source_label, "drive")) and 状态.add_source_card(c):
            cards.append(c)
        if total:
            with 状态.lock:
                状态.scan_progress = (i + 1) / total

    # 通用回退
    if not cards and not entry_files:
        fallback: list[视频卡片] = _递归寻找M4S(root, source_label, "drive")
        for c in fallback:
            if 状态.add_source_card(c):
                cards.append(c)

    return cards


def _扫描ADB文件夹(
    adb: str,
    serial: str,
    remote_path: str,
    root_folder: str,
    source_label: str,
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
    cards: list[视频卡片] = []
    if 状态._scan_cancel.is_set():
        return cards
    try:
        res: 子进程.CompletedProcess = _adb_run(
            adb,
            serial,
            "shell",
            f"ls -1a '{remote_path}'",
            timeout=10,
        )
        if res.returncode != 0:
            return cards
        entries: list[str] = _解析列表输出(res.stdout)
        if "video.m4s" in entries and "audio.m4s" in entries:
            if card := _制作ADB卡片(adb, serial, remote_path, root_folder, source_label):
                cards.append(card)
        else:
            for entry in entries:
                if entry in (".", ".."):
                    continue
                cards.extend(
                    _扫描ADB文件夹(
                        adb,
                        serial,
                        f"{remote_path}/{entry}",
                        root_folder,
                        source_label,
                    )
                )
    except Exception:
        pass
    return cards


def _遍历ADB包(package: str) -> list[tuple[str, str]]:
    requested: str = package.strip()
    if not requested:
        return list(_BILI_PACKAGES)
    if requested in _BILI_PACKAGE_NAMES:
        return [(requested, _BILI_PACKAGE_NAMES[requested])]
    状态.log("warn", f"未知 B 站包名: {requested}")
    return []


def _拉取ADB封面(adb: str, serial: str, remote_dir: str, identifier: str) -> str:
    r"""
    从 ADB 设备拉取 cover.jpg 到本地缓存目录，命中缓存直接返回
    参考 biliandout ScanWorker._pull_cover_adb
    :param: adb: adb 路径
    :param: serial: 设备序列号
    :param: remote_dir: 远端目录（向上搜索起点）
    :param: identifier: 唯一标识（用于哈希命名）
    :return: str: 本地缓存路径, 失败返回空串
    """
    safe_id: str = 哈希.md5(f"{remote_dir}_{identifier}".encode()).hexdigest()
    for ext in ("jpg", "jpeg", "png"):
        cached: 路径 = _COVER_CACHE_DIR / f"{safe_id}.{ext}"
        if cached.exists() and cached.stat().st_size > 0:
            return str(cached)

    cur: str = remote_dir
    for _ in range(4):
        for ext in ("jpg", "jpeg", "png"):
            target: 路径 = _COVER_CACHE_DIR / f"{safe_id}.{ext}"
            try:
                res: 子进程.CompletedProcess = _adb_run(
                    adb,
                    serial,
                    "pull",
                    f"{cur}/cover.{ext}",
                    str(target),
                    timeout=15,
                )
                if res.returncode == 0 and target.exists() and target.stat().st_size > 0:
                    return str(target)
            except Exception:
                pass
            target.unlink(missing_ok=True)
        if "/" not in cur:
            break
        cur = cur.rsplit("/", 1)[0]
    return ""


def _制作ADB卡片(
    adb: str,
    serial: str,
    remote_path: str,
    root_folder: str,
    source_label: str,
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
    title: str = root_folder
    quality: str = ""
    resolution: str = ""
    frame_rate: str = ""
    size_bytes: int = 0
    bvid: str = ""
    avid: str = ""
    up_name: str = ""

    # 尝试从父目录拉取 entry.json
    parent_remote: str = remote_path.rsplit("/", 1)[0] if "/" in remote_path else remote_path
    # 针对新版 B 站 Android 缓存进行路径智能上移
    _parts: list[str] = remote_path.split("/")
    if "download" in _parts:
        idx = _parts.index("download")
        depth = len(_parts) - 1 - idx
        if depth == 3:
            parent_remote = "/".join(_parts[:-2])
        elif depth == 2:
            parent_remote = "/".join(_parts[:-1])
    tmp_path: str = ""
    try:
        with 临时文件.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        pull_res: 子进程.CompletedProcess = _adb_run(
            adb,
            serial,
            "pull",
            f"{parent_remote}/entry.json",
            tmp_path,
            timeout=10,
        )
        if pull_res.returncode == 0 and 路径(tmp_path).exists():
            data: dict = 数据交换.loads(路径(tmp_path).read_text(encoding="utf-8"))
            title = data.get("title", root_folder) or root_folder
            bvid = data.get("bvid", "") or ""
            avid = str(data.get("avid", ""))
            up_name = data.get("owner_name", "")
            quality = data.get("quality_pithy_description", "")
            pd: dict = data.get("page_data", {})
            w, h = pd.get("width", 0), pd.get("height", 0)
            if w and h:
                resolution = f"{w}×{h}"
            size_bytes = data.get("total_bytes", 0)
    except Exception:
        pass
    finally:
        if tmp_path:
            路径(tmp_path).unlink(missing_ok=True)

    # 尝试拉取 index.json 解析分辨率/帧率（与 m4s 同目录）
    if not resolution or not frame_rate:
        idx_tmp: str = ""
        try:
            with 临时文件.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
                idx_tmp = tmp.name
            idx_res: 子进程.CompletedProcess = _adb_run(
                adb,
                serial,
                "pull",
                f"{remote_path}/index.json",
                idx_tmp,
                timeout=10,
            )
            if idx_res.returncode == 0 and 路径(idx_tmp).exists():
                res_r, fr_r, _ = _解析索引JSON(路径(idx_tmp))
                if not resolution and res_r:
                    resolution = res_r
                if fr_r:
                    frame_rate = fr_r
        except Exception:
            pass
        finally:
            if idx_tmp:
                路径(idx_tmp).unlink(missing_ok=True)

    # 从目录名推断画质
    if not quality:
        with 忽略异常(ValueError, IndexError):
            quality = _QN_MAP.get(int(remote_path.rsplit("/", 1)[-1]), "")
    if frame_rate:
        quality = f"{quality} {frame_rate}".strip()

    # 拉取封面（向上 4 层查找）
    cover_path: str = _拉取ADB封面(adb, serial, parent_remote, root_folder)

    # 若 entry.json 未提供大小，通过 stat 获取
    if not size_bytes:
        try:
            stat_res: 子进程.CompletedProcess = _adb_run(
                adb,
                serial,
                "shell",
                f"stat -c %s '{remote_path}/video.m4s' '{remote_path}/audio.m4s'",
                timeout=10,
            )
            if stat_res.returncode == 0:
                size_bytes = sum(int(line.strip()) for line in stat_res.stdout.splitlines() if line.strip().isdigit())
        except Exception:
            pass

    return 视频卡片(
        title=title,
        bvid=bvid,
        avid=avid,
        up_name=up_name,
        quality=quality,
        resolution=resolution,
        size_bytes=size_bytes,
        folder_name=root_folder,
        source_label=source_label,
        source_type="adb",
        device_serial=serial,
        video_path=f"{remote_path}/video.m4s",
        audio_path=f"{remote_path}/audio.m4s",
        cover_path=cover_path,
    )


def _扫描ADB设备(serial: str, source_label: str, package: str = "") -> list[视频卡片]:
    r"""
    扫描 ADB 设备上所有哔哩哔哩包的下载目录
    参考 biliandout ScanWorker._scan_adb
    :param: serial: 设备序列号
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    cards: list[视频卡片] = []
    adb: str | None = _find_adb()
    if not adb:
        状态.log("error", "未找到 ADB 可执行文件，请安装 ADB 并将其加入 PATH")
        return cards

    for pkg, pkg_name in _遍历ADB包(package):
        remote_base: str = f"/sdcard/Android/data/{pkg}/download"
        try:
            res: 子进程.CompletedProcess = _adb_run(
                adb,
                serial,
                "shell",
                f"ls -1a '{remote_base}'",
                timeout=15,
            )
            if res.returncode != 0:
                continue
            folders: list[str] = _解析列表输出(res.stdout)
            total: int = len(folders)
            for i, folder_name in enumerate(folders):
                if 状态._scan_cancel.is_set():
                    break
                while 状态._scan_pause.is_set() and not 状态._scan_cancel.is_set():
                    时间.sleep(0.2)
                for c in _扫描ADB文件夹(
                    adb,
                    serial,
                    f"{remote_base}/{folder_name}",
                    folder_name,
                    source_label,
                ):
                    if 状态.add_source_card(c):
                        cards.append(c)
                if total:
                    with 状态.lock:
                        状态.scan_progress = (i + 1) / total
        except Exception as e:
            状态.log("warn", f"扫描 {pkg_name} 失败: {e}")

    return cards


def _扫描线程函数(
    source_type: str,
    path: str,
    label: str,
    serial: str,
    package: str,
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
        状态.log("info", f"开始扫描: {label}")
        with 状态.lock:
            状态.scan_status = "scanning"
            状态.scan_progress = 0.0

        match source_type:
            case "pc":
                found = _扫描电脑缓存(路径(path), label)
            case "drive":
                found = _扫描磁盘(路径(path), label)
            case "adb":
                found = _扫描ADB设备(serial, label, package)
            case _:
                found = _扫描本地目录(路径(path), label)

        if 工具.取爬虫兜底超时() is not None and not 状态._scan_cancel.is_set():
            with 状态.lock:
                pending: list[视频卡片] = [c for c in 状态.source_cards if not (c.title and c.up_name)]
            for c in pending:
                if 状态._scan_cancel.is_set():
                    break
                _爬虫补全(c)

        with 状态.lock:
            状态.scan_status = "idle"
            状态.scan_progress = 1.0

        if 状态._scan_cancel.is_set():
            状态.log("warn", "扫描已取消")
        else:
            状态.log("success", f"扫描完成: 发现 {len(found)} 个视频")
    except Exception as e:
        状态.log("error", f"扫描异常: {e}")
        with 状态.lock:
            状态.scan_status = "idle"
    finally:
        状态._scan_cancel.clear()
        状态._scan_pause.clear()


# ===== 导出函数 =====


def _构建文件名(card: 视频卡片) -> str:
    r"""
    按设置中的 name_parts 组合导出文件名
    :param: card: 视频卡片
    :return: str: 文件名（含 .mp4），空串表示应跳过
    """
    raw: str = 工具.取设置("localout", "name_parts")
    parts: set[str] = set(raw.split(","))
    action: str = 工具.取设置("localout", "incomplete_title_action")

    display_title: str = card.title
    if not display_title:
        if action == "skip":
            return ""
        display_title = card.folder_name or "untitled"

    segs: list[str] = []
    if "up" in parts and card.up_name:
        segs.append(card.up_name)

    mid: str = ""
    if "bv" in parts and (bv := card.bvid or (f"av{card.avid}" if card.avid else "")):
        mid += f"{{{bv}}}"
    gp: str = ""
    if "group" in parts and card.group_title:
        gp += card.group_title
    if "part" in parts:
        gp += f"[P{card.part}]"
    if gp:
        mid += f"({gp})"
    if mid:
        segs.append(mid)

    if "title" in parts:
        segs.append(display_title)

    main: str = "--".join(segs) if segs else "untitled"
    tails: list[str] = []
    if "publish_time" in parts and card.publish_time:
        tails.append(card.publish_time)
    if "export_time" in parts:
        tails.append(f"导出于{_完整时间()}")
    if tails:
        main += "--" + ",".join(tails)

    return _清理文件名(main) + ".mp4"


def _本地合并(card: 视频卡片, output: str) -> None:
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
    vp: str = card.video_path
    ap: str = card.audio_path

    if not vp or not 路径(vp).exists():
        raise FileNotFoundError(f"视频文件不存在: {vp}")

    if 路径(vp).name.lower() == "video.m4s":
        # Android 标准命名 → combine(父目录, 输出)
        result: bool = _ffm4s.combine(str(路径(vp).parent), output)
    else:
        # PC codec-id 命名 → convert(视频, 音频, 输出)
        if not ap or not 路径(ap).exists():
            raise FileNotFoundError(f"音频文件不存在: {ap}")
        result = _ffm4s.convert(vp, ap, output)

    if not result:
        raise RuntimeError("biliffm4s 合并失败")


def _导出单个ADB(card: 视频卡片, output: str) -> None:
    r"""
    通过 ADB 拉取视频/音频到临时目录后合并为 mp4
    参考 biliandout DeviceScanner.pull_and_convert ADB 分支
    :param: card: 视频卡片（source_type == "adb"）
    :param: output: 输出 mp4 路径
    :raise: RuntimeError: ADB 不可用或拉取/合并失败
    """
    adb: str | None = _find_adb()
    if not adb:
        raise RuntimeError("未找到 ADB 可执行文件")
    serial: str = card.device_serial
    if not serial:
        raise RuntimeError("ADB 设备序列号为空")

    with 临时文件.TemporaryDirectory() as tmp_dir:
        local_video: str = str(路径(tmp_dir) / "video.m4s")
        local_audio: str = str(路径(tmp_dir) / "audio.m4s")

        for remote, local, name in (
            (card.video_path, local_video, "视频"),
            (card.audio_path, local_audio, "音频"),
        ):
            pull_res: 子进程.CompletedProcess = _adb_run(
                adb,
                serial,
                "pull",
                remote,
                local,
                timeout=300,
            )
            if pull_res.returncode != 0:
                raise RuntimeError(f"ADB 拉取{name}失败: {pull_res.stderr.strip()[:120]}")

        # 拉取后标准命名，直接使用 combine
        result: bool = _ffm4s.combine(tmp_dir, output)
        if not result:
            raise RuntimeError("biliffm4s 合并失败")


def _导出单个(card: 视频卡片, output_dir: 路径) -> None:
    r"""
    导出单个视频（自动区分本地与 ADB 来源）
    :param: card: 视频卡片
    :param: output_dir: 输出目录
    """
    if not _HAS_FFM4S:
        raise RuntimeError("biliffm4s 未安装")

    fname: str = _构建文件名(card)
    if not fname:
        raise RuntimeError("标题不完整且策略为跳过")

    output: 路径 = output_dir / fname
    counter: int = 1
    while output.exists():
        output = output_dir / f"{output.stem}_{counter}.mp4"
        counter += 1

    if card.source_type == "adb":
        _导出单个ADB(card, str(output))
    else:
        _本地合并(card, str(output))
    card.output_path = str(output)


def _导出线程函数(card_ids: list[str]) -> None:
    r"""
    导出线程入口函数
    :param: card_ids: 待导出的卡片 ID 列表
    """
    output_dir: 路径 = 工具.取导出路径() / 工具.取设置("localout", "folder")
    output_dir.mkdir(parents=True, exist_ok=True)

    concurrent: int = max(1, min(int(工具.取设置("localout", "ffmpeg_concurrent") or "3"), 32))

    with 状态.lock:
        targets: list[视频卡片] = [c for c in 状态.task_cards if c.id in card_ids]
        状态.export_total = len(targets)
        状态.export_done = 0
        状态.export_progress = 0.0
        状态.export_status = "exporting"

    状态.log("info", f"开始导出 {len(targets)} 个视频 (并发 {concurrent})")

    def _do_one(card: 视频卡片) -> None:
        if 状态._export_cancel.is_set():
            return
        with 状态.lock:
            card.status = "exporting"
        状态.log("info", f"导出中: {card.title or card.folder_name}")
        try:
            _导出单个(card, output_dir)
            with 状态.lock:
                card.status = "success"
                状态.task_cards = [c for c in 状态.task_cards if c.id != card.id]
                状态.completed_cards.append(card)
                状态.export_done += 1
                状态.export_progress = 状态.export_done / 状态.export_total if 状态.export_total else 1
            状态.log("success", f"导出完成: {card.title or card.folder_name}")
        except Exception as e:
            with 状态.lock:
                card.status = "failed"
                card.error = str(e)
                状态.export_done += 1
                状态.export_progress = 状态.export_done / 状态.export_total if 状态.export_total else 1
            状态.log("error", f"导出失败: {card.title or card.folder_name} — {e}")

    with 线程池执行器(max_workers=concurrent) as pool:
        futs: dict = {pool.submit(_do_one, c): c for c in targets}
        for _f in 逐个完成(futs):
            if 状态._export_cancel.is_set():
                break

    with 状态.lock:
        状态.export_status = "idle"
    if 状态._export_cancel.is_set():
        状态.log("warn", "导出已取消")
    else:
        状态.log("success", f"全部导出任务结束 (成功 {状态.export_done}/{状态.export_total})")
    状态._export_cancel.clear()


# ===== 公开 API =====


def 取状态() -> dict:
    r"""
    获取当前状态快照
    :return: dict
    """
    return 状态.snapshot()


def 取环境状态() -> dict:
    r"""
    获取环境状态信息，用于前端显示诊断
    :return: dict: 环境状态
    """
    adb_path: str | None = _find_adb()
    has_ffm4s: bool = _HAS_FFM4S
    has_httpx: bool = _HAS_HTTPX

    return {
        "adb": {
            "available": adb_path is not None,
            "path": adb_path or "",
            "hint": "请安装 ADB 并添加到 PATH，或放入 mybiout/bin/ 目录" if not adb_path else "",
        },
        "biliffm4s": {
            "available": has_ffm4s,
            "hint": "请运行: pip install biliffm4s" if not has_ffm4s else "",
        },
        "httpx": {
            "available": has_httpx,
            "hint": "爬虫补全功能不可用（可选依赖）" if not has_httpx else "",
        },
    }


def 取可用来源() -> dict:
    r"""
    获取可用的扫描源列表
    包括：浏览按钮 / PC 缓存 / 挂载驱动器 Android 设备 / ADB Android 设备
    参考 biliandout DeviceScanner.get_connected_devices
    :return: dict: 包含 sources 列表和 warnings 列表
    """
    warnings: list[str] = []
    sources: list[dict] = [
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
    if not _HAS_FFM4S:
        warnings.append("biliffm4s 未安装，导出功能将不可用")

    adb_path: str | None = _find_adb()
    if not adb_path:
        warnings.append("ADB 未找到，无法扫描 Android 设备（USB调试模式）")

    # PC 桌面端缓存
    pc_path: str = 工具.取设置("localout", "bilibili_pc_cache_path").strip()
    if pc_path:
        optional: bool = 工具.取设置("localout", "bilibili_pc_cache_optional_when_installed") == "true"
        if not (optional and not 路径(pc_path).is_dir()):
            sources.append(
                {
                    "id": "pc_cache",
                    "label": "哔哩哔哩桌面端缓存",
                    "icon": "💻",
                    "type": "pc",
                    "path": pc_path,
                    "serial": "",
                    "package": "",
                }
            )

    # 挂载为本地驱动器的 Android 设备（MTP / USB 大容量存储）
    # 参考 biliandout DeviceScanner.get_drive_devices
    drive_count: int = 0
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        drive: 路径 = 路径(f"{letter}:/")
        if not drive.exists():
            continue
        android_data: 路径 = drive / "Android" / "data"
        if not android_data.exists():
            continue
        device_name: str = _取卷标(letter)
        for pkg, name in _BILI_PACKAGES:
            for download_path in (
                android_data / pkg / "download",
                android_data / pkg / "files" / "download",
            ):
                if download_path.exists():
                    sources.append(
                        {
                            "id": f"drive_{letter}_{pkg}",
                            "label": f"{device_name} 上的{name}",
                            "icon": "📱",
                            "type": "drive",
                            "path": str(download_path),
                            "serial": "",
                            "package": pkg,
                        }
                    )
                    drive_count += 1
                    break

    # ADB 连接的 Android 设备（USB 调试模式）
    # 参考 biliandout DeviceScanner.get_adb_devices
    adb_devices: list[tuple[str, str]] = _get_adb_devices() if adb_path else []
    if adb_path and not adb_devices:
        warnings.append("ADB 已安装但未检测到设备，请确认设备已启用 USB 调试并已授权")

    for serial, display_name in adb_devices:
        for pkg, name in _BILI_PACKAGES:
            sources.append(
                {
                    "id": f"adb_{serial}_{pkg}",
                    "label": f"{display_name} · {name}（ADB）",
                    "icon": "🔌",
                    "type": "adb",
                    "path": "",
                    "serial": serial,
                    "package": pkg,
                }
            )

    now: float = 时间.time()
    if now - 状态._last_available_refresh >= 1.0:
        with 状态.lock:
            状态._last_available_refresh = now
            状态._available_keys = {
                f"{s.get('type', '')}|{s.get('label', '')}" for s in sources if s.get("type") in ("drive", "adb")
            }

    return {"sources": sources, "warnings": warnings}


def 浏览本地() -> str | None:
    r"""
    弹出文件夹对话框选择本地缓存目录
    :return: str | None
    """
    try:
        from tkinter import Tk, filedialog

        root: Tk = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder: str = filedialog.askdirectory(title="选择缓存目录")
        root.destroy()
        return folder if folder else None
    except Exception:
        return None


def 添加来源(
    source_type: str,
    path: str = "",
    label: str = "",
    serial: str = "",
    package: str = "",
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
    source_type = source_type.strip().lower()
    path = path.strip()
    label = label.strip()
    serial = serial.strip()
    package = package.strip()

    with 状态.lock:
        if 状态.scan_status == "scanning":
            return {"ok": False, "error": "已有扫描在进行中"}

    if source_type not in {"pc", "drive", "adb", "local"}:
        return {"ok": False, "error": f"未知扫描源类型: {source_type}"}

    if source_type == "adb":
        if not serial:
            return {"ok": False, "error": "ADB 设备序列号为空"}
        if package and package not in _BILI_PACKAGE_NAMES:
            return {"ok": False, "error": f"未知 B 站包名: {package}"}
    else:
        if not path or not 路径(path).is_dir():
            return {"ok": False, "error": f"路径不存在: {path or '(空)'}"}

    状态._scan_cancel.clear()
    状态._scan_pause.clear()
    t: 线程.Thread = 线程.Thread(
        target=_扫描线程函数,
        args=(source_type, path, label or path or source_type, serial, package),
        daemon=True,
    )
    with 状态.lock:
        状态._scan_thread = t
    t.start()
    return {"ok": True}


def 暂停扫描() -> None:
    状态._scan_pause.set()
    with 状态.lock:
        if 状态.scan_status == "scanning":
            状态.scan_status = "paused"
    状态.log("info", "扫描已暂停")


def 继续扫描() -> None:
    状态._scan_pause.clear()
    with 状态.lock:
        if 状态.scan_status == "paused":
            状态.scan_status = "scanning"
    状态.log("info", "扫描已继续")


def 取消扫描() -> None:
    状态._scan_cancel.set()
    状态._scan_pause.clear()
    with 状态.lock:
        状态.scan_status = "idle"


def 加入任务(card_ids: list[str]) -> dict:
    r"""
    将源卡片添加到任务栏
    :param: card_ids: 源卡片 ID 列表
    :return: dict
    """
    added: int = 0
    with 状态.lock:
        existing: set[tuple[str, str]] = {(c.video_path, c.audio_path) for c in 状态.task_cards}
        for sid in card_ids:
            for sc in 状态.source_cards:
                if sc.id == sid:
                    key: tuple[str, str] = (sc.video_path, sc.audio_path)
                    if key not in existing:
                        状态.task_cards.append(sc.clone())
                        existing.add(key)
                        added += 1
                    break
    状态.log("info", f"已添加 {added} 个视频到任务栏")
    return {"ok": True, "added": added}


def 移除来源卡片(card_ids: list[str]) -> None:
    r"""
    移除指定源卡片
    :param: card_ids: 卡片 ID 列表
    """
    ids: set[str] = set(card_ids)
    with 状态.lock:
        removed: list[视频卡片] = [c for c in 状态.source_cards if c.id in ids]
        状态.source_cards = [c for c in 状态.source_cards if c.id not in ids]
        for c in removed:
            状态._known_keys.discard(状态._dedup_key(c))


def 移除任务卡片(card_ids: list[str]) -> None:
    r"""
    移除指定任务卡片
    :param: card_ids: 卡片 ID 列表
    """
    ids: set[str] = set(card_ids)
    with 状态.lock:
        状态.task_cards = [c for c in 状态.task_cards if c.id not in ids]


def 清空来源() -> None:
    with 状态.lock:
        状态.source_cards.clear()
        状态._known_keys.clear()
    状态.log("info", "源栏已清空")


def 清空任务() -> None:
    with 状态.lock:
        状态.task_cards = [c for c in 状态.task_cards if c.status == "exporting"]
    状态.log("info", "任务栏已清空 (导出中的任务保留)")


def 清空完成() -> None:
    with 状态.lock:
        状态.completed_cards.clear()
    状态.log("info", "完成栏已清空")


def 开始导出(card_ids: list[str]) -> dict:
    r"""
    开始导出任务
    :param: card_ids: 待导出卡片 ID，为空则导出全部排队中的任务
    :return: dict
    """
    with 状态.lock:
        if 状态.export_status == "exporting":
            return {"ok": False, "error": "导出正在进行中"}
    if not card_ids:
        with 状态.lock:
            card_ids = [c.id for c in 状态.task_cards if c.status == "queued"]
    if not card_ids:
        return {"ok": False, "error": "没有可导出的任务"}

    状态._export_cancel.clear()
    t: 线程.Thread = 线程.Thread(
        target=_导出线程函数,
        args=(card_ids,),
        daemon=True,
    )
    with 状态.lock:
        状态._export_thread = t
    t.start()
    return {"ok": True}


def 取消导出() -> None:
    状态._export_cancel.set()
    状态.log("info", "正在取消导出...")


def 取封面字节(card_id: str) -> tuple[bytes, str] | None:
    r"""
    根据卡片 id 取出封面字节
    :param: card_id: 卡片 id
    :return: (字节, content-type) 或 None
    """
    with 状态.lock:
        pool: list[视频卡片] = 状态.source_cards + 状态.task_cards + 状态.completed_cards
        for c in pool:
            if c.id != card_id or not c.cover_path:
                continue
            p: 路径 = 路径(c.cover_path)
            if not p.exists():
                continue
            suffix: str = p.suffix.lower()
            ct: str = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
            try:
                return p.read_bytes(), ct
            except OSError:
                return None
    return None


_uid = _生成编号
_ts = _短时间
_ts_full = _完整时间
_get_volume_label = _取卷标
_sanitize = _清理文件名
_size_mb = _兆字节
VideoCard = 视频卡片
_State = _本地状态
S = 状态
_parse_entry_json = _解析入口JSON
_find_m4s_recursive = _递归寻找M4S
_parse_ls_output = _解析列表输出
_find_pc_m4s = _寻找电脑M4S
_parse_video_info_json = _解析视频信息JSON
_parse_index_json = _解析索引JSON
_find_cover_upward = _向上寻找封面
_make_card_from_m4s_dir = _从M4S目录制卡
_crawler_enrich = _爬虫补全
_scan_local_dir = _扫描本地目录
_scan_pc_cache = _扫描电脑缓存
_scan_drive = _扫描磁盘
_scan_adb_folder = _扫描ADB文件夹
_iter_adb_packages = _遍历ADB包
_pull_cover_adb = _拉取ADB封面
_make_adb_card = _制作ADB卡片
_scan_adb_device = _扫描ADB设备
_scan_thread_fn = _扫描线程函数
_build_filename = _构建文件名
_local_combine = _本地合并
_export_adb_single = _导出单个ADB
_export_single = _导出单个
_export_thread_fn = _导出线程函数
get_state = 取状态
get_env_status = 取环境状态
get_available_sources = 取可用来源
browse_local = 浏览本地
add_source = 添加来源
pause_scan = 暂停扫描
resume_scan = 继续扫描
cancel_scan = 取消扫描
add_to_tasks = 加入任务
remove_source_cards = 移除来源卡片
remove_task_cards = 移除任务卡片
clear_source = 清空来源
clear_tasks = 清空任务
clear_completed = 清空完成
start_export = 开始导出
cancel_export = 取消导出
get_cover_bytes = 取封面字节
