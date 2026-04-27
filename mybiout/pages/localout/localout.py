r"""
LocalOut! 本地缓存导出服务层, 负责扫描、解析和导出本地视频缓存

:file: mybiout/pages/localout/localout.py
:author: WaterRun
:time: 2026-04-12
"""

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from mybiout.pages import utils

try:
    import httpx
    _HAS_HTTPX: bool = True
except Exception:
    httpx = None
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

_CRAWLER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}

_QN_MAP: dict[int, str] = {
    127: "8K 超高清", 126: "杜比视界", 125: "HDR 真彩", 120: "4K 超清",
    116: "1080P 60帧", 112: "1080P 高码率", 80: "1080P 高清", 74: "720P 60帧",
    64: "720P 高清", 32: "480P 清晰", 16: "360P 流畅", 6: "240P 极速",
}

_AUDIO_CODEC_THRESHOLD: int = 30200

_POPEN_EXTRA: dict = {}
if sys.platform == "win32":
    _POPEN_EXTRA["creationflags"] = 0x08000000


# ===== ADB 工具 =====

def _find_adb() -> str | None:
    r"""
    查找 adb 可执行文件路径（参考 biliandout DeviceScanner.find_adb）
    :return: str | None: 路径, 未找到返回 None
    """
    if shutil.which("adb"):
        return "adb"
    if sys.platform == "win32":
        for candidate in (
            Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local" / "Android"
            / "Sdk" / "platform-tools" / "adb.exe",
            Path("C:/Android/sdk/platform-tools/adb.exe"),
            Path("C:/Program Files/Android/platform-tools/adb.exe"),
            Path("C:/Program Files (x86)/Android/platform-tools/adb.exe"),
        ):
            if candidate.exists():
                return str(candidate)
    return None


def _adb_run(adb: str, serial: str, *args: str, timeout: float = 10) -> subprocess.CompletedProcess:
    r"""
    执行 adb -s serial <args> 命令
    :param: adb: adb 可执行文件路径
    :param: serial: 设备序列号
    :param: args: 后续命令参数
    :param: timeout: 超时秒数
    :return: subprocess.CompletedProcess
    """
    return subprocess.run(
        [adb, "-s", serial, *args],
        capture_output=True, text=True, timeout=timeout,
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
        result: subprocess.CompletedProcess = subprocess.run(
            [adb, "devices", "-l"],
            capture_output=True, text=True, timeout=8,
            **_POPEN_EXTRA,
        )
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

def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _ts_full() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _get_volume_label(letter: str) -> str:
    r"""
    获取驱动器卷标
    :param: letter: 单个大写盘符字母
    :return: str: 卷标名称
    """
    if sys.platform == "win32":
        buf: ctypes.Array = ctypes.create_unicode_buffer(261)
        try:
            ret: int = ctypes.windll.kernel32.GetVolumeInformationW(
                f"{letter}:\\", buf, 261, None, None, None, None, 0,
            )
            if ret and buf.value:
                return buf.value
        except Exception:
            pass
    return f"存储设备 ({letter}:)"


def _sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")
    return name[:200] if name else "untitled"


def _size_mb(b: int | float) -> float:
    return round(b / 1048576, 1) if b else 0


# ===== 数据模型 =====

@dataclass(slots=True)
class VideoCard:
    r"""
    视频缓存卡片数据模型, 表示一个被扫描到的缓存视频
    """
    id: str = field(default_factory=_uid)
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
            alive = Path(self.video_path).exists()
        return {
            "id": self.id, "title": self.title, "bvid": self.bvid, "avid": self.avid,
            "up_name": self.up_name, "group_title": self.group_title, "part": self.part,
            "quality": self.quality, "resolution": self.resolution,
            "size_bytes": self.size_bytes, "size_mb": _size_mb(self.size_bytes),
            "publish_time": self.publish_time, "folder_name": self.folder_name,
            "source_label": self.source_label, "source_type": self.source_type,
            "cover_url": f"/api/localout/cover/{self.id}" if self.cover_path else "",
            "video_path": self.video_path,
            "output_path": self.output_path,
            "path_display": self.output_path or str(Path(self.video_path).parent if self.video_path else ""),
            "alive": alive,
            "status": self.status, "error": self.error,
        }

    def clone(self) -> "VideoCard":
        return replace(self, id=_uid(), status="queued", error="", output_path="")


# ===== 全局状态 =====

class _State:
    r"""
    LocalOut 全局运行状态管理
    """

    def __init__(self) -> None:
        self.lock: threading.RLock = threading.RLock()
        self.source_cards: list[VideoCard] = []
        self.task_cards: list[VideoCard] = []
        self.completed_cards: list[VideoCard] = []
        self.logs: list[dict] = []
        self.scan_status: str = "idle"
        self.scan_progress: float = 0.0
        self.export_status: str = "idle"
        self.export_progress: float = 0.0
        self.export_total: int = 0
        self.export_done: int = 0
        self._scan_thread: threading.Thread | None = None
        self._scan_cancel: threading.Event = threading.Event()
        self._scan_pause: threading.Event = threading.Event()
        self._export_thread: threading.Thread | None = None
        self._export_cancel: threading.Event = threading.Event()
        self._known_keys: set[str] = set()
        self._available_keys: set[str] = set()
        self._last_available_refresh: float = 0.0

    def log(self, level: str, msg: str) -> None:
        with self.lock:
            self.logs.append({"time": _ts(), "level": level, "msg": msg})
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

    def _dedup_key(self, c: VideoCard) -> str:
        # 含 device_serial 避免不同 ADB 设备的相同路径发生碰撞
        return f"{c.source_type}|{c.device_serial}|{c.video_path}|{c.audio_path}"

    def add_source_card(self, c: VideoCard) -> bool:
        k: str = self._dedup_key(c)
        with self.lock:
            if k in self._known_keys:
                return False
            self._known_keys.add(k)
            self.source_cards.append(c)
            return True


S: _State = _State()


# ===== 解析 / 查找函数 =====

def _parse_entry_json(
    path: Path, source_label: str, source_type: str, serial: str = "",
) -> VideoCard | None:
    r"""
    解析安卓缓存 entry.json 文件
    :param: path: entry.json 路径
    :param: source_label: 来源标签
    :param: source_type: 来源类型
    :param: serial: ADB 设备序列号
    :return: VideoCard | None
    """
    try:
        data: dict = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    page_data: dict = data.get("page_data") or {}
    w: int = page_data.get("width", 0)
    h: int = page_data.get("height", 0)
    type_tag: str = str(data.get("type_tag", ""))
    parent_dir: Path = path.parent

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

    return VideoCard(
        title=data.get("title", ""), bvid=data.get("bvid", "") or "",
        avid=str(data.get("avid", "")), up_name=data.get("owner_name", ""),
        part=page_data.get("page", 1), quality=data.get("quality_pithy_description", ""),
        resolution=f"{w}×{h}" if w and h else "",
        size_bytes=data.get("total_bytes", 0), folder_name=parent_dir.name,
        source_label=source_label, source_type=source_type,
        device_serial=serial, video_path=video_path, audio_path=audio_path,
        cover_path=_find_cover_upward(parent_dir),
    )


def _find_m4s_recursive(root: Path, source_label: str, source_type: str) -> list[VideoCard]:
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
    cards: list[VideoCard] = []
    vp: Path = root / "video.m4s"
    ap: Path = root / "audio.m4s"
    if vp.exists() and ap.exists():
        if card := _make_card_from_m4s_dir(root, source_label, source_type):
            cards.append(card)
    else:
        try:
            for sub in root.iterdir():
                if sub.is_dir():
                    cards.extend(_find_m4s_recursive(sub, source_label, source_type))
        except PermissionError:
            pass
    return cards


def _find_pc_m4s(cache_dir: Path) -> tuple[str, str]:
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


def _parse_video_info_json(path: Path, source_label: str) -> VideoCard | None:
    r"""
    解析 PC 缓存 videoInfo.json 文件
    :param: path: videoInfo.json 路径
    :param: source_label: 来源标签
    :return: VideoCard | None
    """
    try:
        data: dict = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    qn: int = data.get("qn", 0)
    pubdate: int = data.get("pubdate", 0)
    publish_time: str = ""
    if pubdate:
        try:
            publish_time = datetime.fromtimestamp(pubdate).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

    cache_dir: Path = path.parent
    video_path, audio_path = _find_pc_m4s(cache_dir)
    if not video_path:
        return None

    return VideoCard(
        title=data.get("title", "") or data.get("groupTitle", ""),
        bvid=data.get("bvid", "") or "", avid=str(data.get("aid", "") or ""),
        up_name=data.get("uname", ""), group_title=data.get("groupTitle", "") or "",
        part=data.get("p", 1), quality=_QN_MAP.get(qn, str(qn) if qn else ""),
        size_bytes=data.get("totalSize", 0), publish_time=publish_time,
        folder_name=cache_dir.name, source_label=source_label, source_type="pc",
        video_path=video_path, audio_path=audio_path,
        cover_path=_find_cover_upward(cache_dir),
    )


def _parse_index_json(path: Path) -> tuple[str, str, int]:
    r"""
    解析 Android 新版 index.json (与 video.m4s/audio.m4s 同目录)
    :param: path: index.json 路径
    :return: (分辨率字符串, 帧率字符串, 视频码率)
    """
    try:
        data: dict = json.loads(path.read_text(encoding="utf-8"))
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
        except (ValueError, TypeError):
            pass
    return resolution, frame_rate, int(v.get("bandwidth", 0) or 0)


def _find_cover_upward(start: Path, max_depth: int = 3) -> str:
    r"""
    从 start 起向上查找 cover.jpg / cover.jpeg / cover.png (含 start 自身)
    :param: start: 起始目录
    :param: max_depth: 最多上溯层数
    :return: str: cover 路径, 找不到返回空串
    """
    cur: Path = start
    for _ in range(max_depth + 1):
        for name in ("cover.jpg", "cover.jpeg", "cover.png"):
            cand: Path = cur / name
            if cand.exists():
                return str(cand)
        if cur.parent == cur:
            break
        cur = cur.parent
    return ""


def _make_card_from_m4s_dir(m4s_dir: Path, source_label: str, source_type: str) -> VideoCard | None:
    r"""
    针对 "目录中含 video.m4s + audio.m4s" 的通用情况构造 VideoCard
    自动尝试解析同目录下 index.json 与上溯查找封面
    :param: m4s_dir: 包含两个 m4s 文件的目录
    :param: source_label: 来源标签
    :param: source_type: 来源类型
    :return: VideoCard | None
    """
    vp: Path = m4s_dir / "video.m4s"
    ap: Path = m4s_dir / "audio.m4s"
    if not (vp.exists() and ap.exists()):
        return None

    size: int = 0
    try:
        size = vp.stat().st_size + ap.stat().st_size
    except OSError:
        pass

    resolution: str = ""
    frame_rate: str = ""
    if (idx := m4s_dir / "index.json").exists():
        resolution, frame_rate, _ = _parse_index_json(idx)

    quality: str = ""
    try:
        quality = _QN_MAP.get(int(m4s_dir.name), "")
    except ValueError:
        pass
    if frame_rate:
        quality = f"{quality} {frame_rate}".strip()

    folder: Path = m4s_dir.parent if m4s_dir.parent != m4s_dir else m4s_dir
    return VideoCard(
        folder_name=folder.name or m4s_dir.name,
        source_label=source_label,
        source_type=source_type,
        video_path=str(vp),
        audio_path=str(ap),
        size_bytes=size,
        resolution=resolution,
        quality=quality,
        cover_path=_find_cover_upward(m4s_dir.parent),
    )


def _crawler_enrich(card: VideoCard) -> None:
    r"""
    若设置启用爬虫降级, 当卡片缺失关键元数据(title/up)时, 尝试用 BV 号补全
    :param: card: 待补全卡片 (就地修改)
    """
    timeout: float | None = utils.get_crawler_fallback_timeout()
    if timeout is None or not _HAS_HTTPX:
        return
    if card.title and card.up_name:
        return
    if not card.bvid:
        if m := re.search(r"(BV[\w]{10,})", card.folder_name or ""):
            card.bvid = m.group(1)
        else:
            return
    try:
        with httpx.Client(headers=_CRAWLER_HEADERS, timeout=timeout) as c:
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
            try:
                card.publish_time = datetime.fromtimestamp(pubdate).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
    except Exception:
        pass


# ===== 扫描函数 =====

def _scan_local_dir(root: Path, source_label: str) -> list[VideoCard]:
    r"""
    扫描本地目录：优先解析 entry.json / videoInfo.json，
    若均无则递归查找任意 video.m4s / audio.m4s 对
    :param: root: 根目录
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    cards: list[VideoCard] = []
    entry_files: list[Path] = list(root.rglob("entry.json"))
    vi_files: list[Path] = list(root.rglob("videoInfo.json"))
    total: int = len(entry_files) + len(vi_files)

    for i, ef in enumerate(entry_files):
        if S._scan_cancel.is_set():
            break
        while S._scan_pause.is_set() and not S._scan_cancel.is_set():
            time.sleep(0.2)
        if (c := _parse_entry_json(ef, source_label, "local")) and S.add_source_card(c):
            cards.append(c)
        if total:
            with S.lock:
                S.scan_progress = (i + 1) / total

    for i, vf in enumerate(vi_files):
        if S._scan_cancel.is_set():
            break
        while S._scan_pause.is_set() and not S._scan_cancel.is_set():
            time.sleep(0.2)
        if (c := _parse_video_info_json(vf, source_label)) and S.add_source_card(c):
            cards.append(c)
        if total:
            with S.lock:
                S.scan_progress = (len(entry_files) + i + 1) / total

    # 通用回退：当目录中没有任何 JSON 元数据时，递归查找 m4s 对
    if not cards and not entry_files and not vi_files:
        fallback: list[VideoCard] = _find_m4s_recursive(root, source_label, "local")
        for c in fallback:
            if S.add_source_card(c):
                cards.append(c)

    return cards


def _scan_pc_cache(root: Path, source_label: str) -> list[VideoCard]:
    r"""
    扫描 PC 桌面端缓存目录
    :param: root: 缓存根目录
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    cards: list[VideoCard] = []
    if not root.is_dir():
        S.log("error", f"PC 缓存路径不存在: {root}")
        return cards

    subdirs: list[Path] = [d for d in root.iterdir() if d.is_dir()]
    total: int = len(subdirs)

    for i, sd in enumerate(subdirs):
        if S._scan_cancel.is_set():
            break
        while S._scan_pause.is_set() and not S._scan_cancel.is_set():
            time.sleep(0.2)

        if (vf := sd / "videoInfo.json").exists():
            if (c := _parse_video_info_json(vf, source_label)) and S.add_source_card(c):
                cards.append(c)
        else:
            video, audio = _find_pc_m4s(sd)
            if video:
                c = VideoCard(
                    folder_name=sd.name, source_label=source_label,
                    source_type="pc", video_path=video, audio_path=audio,
                    cover_path=_find_cover_upward(Path(video).parent),
                )
                if S.add_source_card(c):
                    cards.append(c)
            else:
                for nested in _find_m4s_recursive(sd, source_label, "pc"):
                    if S.add_source_card(nested):
                        cards.append(nested)

        if total:
            with S.lock:
                S.scan_progress = (i + 1) / total

    return cards


def _scan_drive(root: Path, source_label: str) -> list[VideoCard]:
    r"""
    扫描挂载为本地驱动器的 Android 设备缓存
    :param: root: 下载目录（如 E:/Android/data/tv.danmaku.bili/download）
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    cards: list[VideoCard] = []
    if not root.is_dir():
        S.log("error", f"驱动器缓存路径不存在: {root}")
        return cards

    entry_files: list[Path] = list(root.rglob("entry.json"))
    total: int = len(entry_files)

    for i, ef in enumerate(entry_files):
        if S._scan_cancel.is_set():
            break
        while S._scan_pause.is_set() and not S._scan_cancel.is_set():
            time.sleep(0.2)
        if (c := _parse_entry_json(ef, source_label, "drive")) and S.add_source_card(c):
            cards.append(c)
        if total:
            with S.lock:
                S.scan_progress = (i + 1) / total

    # 通用回退
    if not cards and not entry_files:
        fallback: list[VideoCard] = _find_m4s_recursive(root, source_label, "drive")
        for c in fallback:
            if S.add_source_card(c):
                cards.append(c)

    return cards


def _scan_adb_folder(
    adb: str, serial: str, remote_path: str, root_folder: str, source_label: str,
) -> list[VideoCard]:
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
    cards: list[VideoCard] = []
    if S._scan_cancel.is_set():
        return cards
    try:
        res: subprocess.CompletedProcess = _adb_run(
            adb, serial, "shell", f"ls '{remote_path}'", timeout=10,
        )
        if res.returncode != 0:
            return cards
        entries: list[str] = [
            line.strip() for line in res.stdout.splitlines()
            if line.strip() and not line.strip().startswith("ls:")
        ]
        if "video.m4s" in entries and "audio.m4s" in entries:
            if card := _make_adb_card(adb, serial, remote_path, root_folder, source_label):
                cards.append(card)
        else:
            for entry in entries:
                if entry in (".", ".."):
                    continue
                cards.extend(_scan_adb_folder(
                    adb, serial, f"{remote_path}/{entry}", root_folder, source_label,
                ))
    except Exception:
        pass
    return cards


def _make_adb_card(
    adb: str, serial: str, remote_path: str, root_folder: str, source_label: str,
) -> VideoCard | None:
    r"""
    解析 ADB 设备上某 m4s 目录，尝试拉取 entry.json 获取元数据后生成 VideoCard
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
    size_bytes: int = 0

    # 尝试从父目录拉取 entry.json
    parent_remote: str = remote_path.rsplit("/", 1)[0] if "/" in remote_path else remote_path
    tmp_path: str = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name
        pull_res: subprocess.CompletedProcess = _adb_run(
            adb, serial, "pull", f"{parent_remote}/entry.json", tmp_path, timeout=10,
        )
        if pull_res.returncode == 0 and Path(tmp_path).exists():
            data: dict = json.loads(Path(tmp_path).read_text(encoding="utf-8"))
            title = data.get("title", root_folder) or root_folder
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
            Path(tmp_path).unlink(missing_ok=True)

    # 从目录名推断画质
    if not quality:
        try:
            quality = _QN_MAP.get(int(remote_path.rsplit("/", 1)[-1]), "")
        except (ValueError, IndexError):
            pass

    # 若 entry.json 未提供大小，通过 stat 获取
    if not size_bytes:
        try:
            stat_res: subprocess.CompletedProcess = _adb_run(
                adb, serial, "shell",
                f"stat -c %s '{remote_path}/video.m4s' '{remote_path}/audio.m4s'",
                timeout=10,
            )
            if stat_res.returncode == 0:
                size_bytes = sum(
                    int(line.strip())
                    for line in stat_res.stdout.splitlines()
                    if line.strip().isdigit()
                )
        except Exception:
            pass

    return VideoCard(
        title=title, quality=quality, resolution=resolution,
        size_bytes=size_bytes, folder_name=root_folder,
        source_label=source_label, source_type="adb",
        device_serial=serial,
        video_path=f"{remote_path}/video.m4s",
        audio_path=f"{remote_path}/audio.m4s",
    )


def _scan_adb_device(serial: str, source_label: str) -> list[VideoCard]:
    r"""
    扫描 ADB 设备上所有哔哩哔哩包的下载目录
    参考 biliandout ScanWorker._scan_adb
    :param: serial: 设备序列号
    :param: source_label: 来源标签
    :return: list[VideoCard]
    """
    cards: list[VideoCard] = []
    adb: str | None = _find_adb()
    if not adb:
        S.log("error", "未找到 ADB 可执行文件，请安装 ADB 并将其加入 PATH")
        return cards

    for pkg, pkg_name in _BILI_PACKAGES:
        remote_base: str = f"/sdcard/Android/data/{pkg}/download"
        try:
            res: subprocess.CompletedProcess = _adb_run(
                adb, serial, "shell", f"ls '{remote_base}'", timeout=15,
            )
            if res.returncode != 0:
                continue
            folders: list[str] = [
                line.strip() for line in res.stdout.splitlines()
                if line.strip() and not line.strip().startswith("ls:")
            ]
            total: int = len(folders)
            for i, folder_name in enumerate(folders):
                if S._scan_cancel.is_set():
                    break
                while S._scan_pause.is_set() and not S._scan_cancel.is_set():
                    time.sleep(0.2)
                for c in _scan_adb_folder(
                    adb, serial, f"{remote_base}/{folder_name}", folder_name, source_label,
                ):
                    if S.add_source_card(c):
                        cards.append(c)
                if total:
                    with S.lock:
                        S.scan_progress = (i + 1) / total
        except Exception as e:
            S.log("warn", f"扫描 {pkg_name} 失败: {e}")

    return cards


def _scan_thread_fn(
    source_type: str, path: str, label: str, serial: str, package: str,
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
        S.log("info", f"开始扫描: {label}")
        with S.lock:
            S.scan_status = "scanning"
            S.scan_progress = 0.0

        match source_type:
            case "pc":
                found = _scan_pc_cache(Path(path), label)
            case "drive":
                found = _scan_drive(Path(path), label)
            case "adb":
                found = _scan_adb_device(serial, label)
            case _:
                found = _scan_local_dir(Path(path), label)

        if utils.get_crawler_fallback_timeout() is not None and not S._scan_cancel.is_set():
            with S.lock:
                pending: list[VideoCard] = [c for c in S.source_cards if not (c.title and c.up_name)]
            for c in pending:
                if S._scan_cancel.is_set():
                    break
                _crawler_enrich(c)

        with S.lock:
            S.scan_status = "idle"
            S.scan_progress = 1.0

        if S._scan_cancel.is_set():
            S.log("warn", "扫描已取消")
        else:
            S.log("success", f"扫描完成: 发现 {len(found)} 个视频")
    except Exception as e:
        S.log("error", f"扫描异常: {e}")
        with S.lock:
            S.scan_status = "idle"
    finally:
        S._scan_cancel.clear()
        S._scan_pause.clear()


# ===== 导出函数 =====

def _build_filename(card: VideoCard) -> str:
    r"""
    按设置中的 name_parts 组合导出文件名
    :param: card: 视频卡片
    :return: str: 文件名（含 .mp4），空串表示应跳过
    """
    raw: str = utils.get_setting("localout", "name_parts")
    parts: set[str] = set(raw.split(","))
    action: str = utils.get_setting("localout", "incomplete_title_action")

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
        tails.append(f"导出于{_ts_full()}")
    if tails:
        main += "--" + ",".join(tails)

    return _sanitize(main) + ".mp4"


def _local_combine(card: VideoCard, output: str) -> None:
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

    if not vp or not Path(vp).exists():
        raise FileNotFoundError(f"视频文件不存在: {vp}")

    if Path(vp).name.lower() == "video.m4s":
        # Android 标准命名 → combine(父目录, 输出)
        result: bool = _ffm4s.combine(str(Path(vp).parent), output)
    else:
        # PC codec-id 命名 → convert(视频, 音频, 输出)
        if not ap or not Path(ap).exists():
            raise FileNotFoundError(f"音频文件不存在: {ap}")
        result = _ffm4s.convert(vp, ap, output)

    if not result:
        raise RuntimeError("biliffm4s 合并失败")


def _export_adb_single(card: VideoCard, output: str) -> None:
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

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_video: str = str(Path(tmp_dir) / "video.m4s")
        local_audio: str = str(Path(tmp_dir) / "audio.m4s")

        for remote, local, name in (
            (card.video_path, local_video, "视频"),
            (card.audio_path, local_audio, "音频"),
        ):
            pull_res: subprocess.CompletedProcess = _adb_run(
                adb, serial, "pull", remote, local, timeout=300,
            )
            if pull_res.returncode != 0:
                raise RuntimeError(
                    f"ADB 拉取{name}失败: {pull_res.stderr.strip()[:120]}"
                )

        # 拉取后标准命名，直接使用 combine
        result: bool = _ffm4s.combine(tmp_dir, output)
        if not result:
            raise RuntimeError("biliffm4s 合并失败")


def _export_single(card: VideoCard, output_dir: Path) -> None:
    r"""
    导出单个视频（自动区分本地与 ADB 来源）
    :param: card: 视频卡片
    :param: output_dir: 输出目录
    """
    if not _HAS_FFM4S:
        raise RuntimeError("biliffm4s 未安装")

    fname: str = _build_filename(card)
    if not fname:
        raise RuntimeError("标题不完整且策略为跳过")

    output: Path = output_dir / fname
    counter: int = 1
    while output.exists():
        output = output_dir / f"{output.stem}_{counter}.mp4"
        counter += 1

    if card.source_type == "adb":
        _export_adb_single(card, str(output))
    else:
        _local_combine(card, str(output))
    card.output_path = str(output)


def _export_thread_fn(card_ids: list[str]) -> None:
    r"""
    导出线程入口函数
    :param: card_ids: 待导出的卡片 ID 列表
    """
    output_dir: Path = utils.get_export_path() / utils.get_setting("localout", "folder")
    output_dir.mkdir(parents=True, exist_ok=True)

    concurrent: int = max(1, min(int(utils.get_setting("localout", "ffmpeg_concurrent") or "3"), 32))

    with S.lock:
        targets: list[VideoCard] = [c for c in S.task_cards if c.id in card_ids]
        S.export_total = len(targets)
        S.export_done = 0
        S.export_progress = 0.0
        S.export_status = "exporting"

    S.log("info", f"开始导出 {len(targets)} 个视频 (并发 {concurrent})")

    def _do_one(card: VideoCard) -> None:
        if S._export_cancel.is_set():
            return
        with S.lock:
            card.status = "exporting"
        S.log("info", f"导出中: {card.title or card.folder_name}")
        try:
            _export_single(card, output_dir)
            with S.lock:
                card.status = "success"
                S.task_cards = [c for c in S.task_cards if c.id != card.id]
                S.completed_cards.append(card)
                S.export_done += 1
                S.export_progress = S.export_done / S.export_total if S.export_total else 1
            S.log("success", f"导出完成: {card.title or card.folder_name}")
        except Exception as e:
            with S.lock:
                card.status = "failed"
                card.error = str(e)
                S.export_done += 1
                S.export_progress = S.export_done / S.export_total if S.export_total else 1
            S.log("error", f"导出失败: {card.title or card.folder_name} — {e}")

    with ThreadPoolExecutor(max_workers=concurrent) as pool:
        futs: dict = {pool.submit(_do_one, c): c for c in targets}
        for f in as_completed(futs):
            if S._export_cancel.is_set():
                break

    with S.lock:
        S.export_status = "idle"
    if S._export_cancel.is_set():
        S.log("warn", "导出已取消")
    else:
        S.log("success", f"全部导出任务结束 (成功 {S.export_done}/{S.export_total})")
    S._export_cancel.clear()


# ===== 公开 API =====

def get_state() -> dict:
    r"""
    获取当前状态快照
    :return: dict
    """
    return S.snapshot()


def get_available_sources() -> list[dict]:
    r"""
    获取可用的扫描源列表
    包括：浏览按钮 / PC 缓存 / 挂载驱动器 Android 设备 / ADB Android 设备
    参考 biliandout DeviceScanner.get_connected_devices
    :return: list[dict]
    """
    sources: list[dict] = [
        {"id": "browse", "label": "浏览本地路径...", "icon": "📂",
         "type": "browse", "path": "", "serial": "", "package": ""},
    ]

    # PC 桌面端缓存
    pc_path: str = utils.get_setting("localout", "bilibili_pc_cache_path").strip()
    if pc_path:
        optional: bool = (
            utils.get_setting("localout", "bilibili_pc_cache_optional_when_installed") == "true"
        )
        if not (optional and not Path(pc_path).is_dir()):
            sources.append({
                "id": "pc_cache",
                "label": "哔哩哔哩桌面端缓存",
                "icon": "💻",
                "type": "pc",
                "path": pc_path,
                "serial": "",
                "package": "",
            })

    # 挂载为本地驱动器的 Android 设备（MTP / USB 大容量存储）
    # 参考 biliandout DeviceScanner.get_drive_devices
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        drive: Path = Path(f"{letter}:/")
        if not drive.exists():
            continue
        android_data: Path = drive / "Android" / "data"
        if not android_data.exists():
            continue
        device_name: str = _get_volume_label(letter)
        for pkg, name in _BILI_PACKAGES:
            for download_path in (
                android_data / pkg / "download",
                android_data / pkg / "files" / "download",
            ):
                if download_path.exists():
                    sources.append({
                        "id": f"drive_{letter}_{pkg}",
                        "label": f"{device_name} 上的{name}",
                        "icon": "📱",
                        "type": "drive",
                        "path": str(download_path),
                        "serial": "",
                        "package": pkg,
                    })
                    break

    # ADB 连接的 Android 设备（USB 调试模式）
    # 参考 biliandout DeviceScanner.get_adb_devices
    for serial, display_name in _get_adb_devices():
        for pkg, name in _BILI_PACKAGES:
            sources.append({
                "id": f"adb_{serial}_{pkg}",
                "label": f"{display_name} · {name}（ADB）",
                "icon": "🔌",
                "type": "adb",
                "path": "",
                "serial": serial,
                "package": pkg,
            })

    now: float = time.time()
    if now - S._last_available_refresh >= 1.0:
        with S.lock:
            S._last_available_refresh = now
            S._available_keys = {
                f"{s.get('type', '')}|{s.get('label', '')}"
                for s in sources
                if s.get("type") in ("drive", "adb")
            }

    return sources


def browse_local() -> str | None:
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


def add_source(
    source_type: str, path: str = "", label: str = "",
    serial: str = "", package: str = "",
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
    with S.lock:
        if S.scan_status == "scanning":
            return {"ok": False, "error": "已有扫描在进行中"}

    S._scan_cancel.clear()
    S._scan_pause.clear()
    t: threading.Thread = threading.Thread(
        target=_scan_thread_fn,
        args=(source_type, path, label or path or source_type, serial, package),
        daemon=True,
    )
    with S.lock:
        S._scan_thread = t
    t.start()
    return {"ok": True}


def pause_scan() -> None:
    S._scan_pause.set()
    with S.lock:
        if S.scan_status == "scanning":
            S.scan_status = "paused"
    S.log("info", "扫描已暂停")


def resume_scan() -> None:
    S._scan_pause.clear()
    with S.lock:
        if S.scan_status == "paused":
            S.scan_status = "scanning"
    S.log("info", "扫描已继续")


def cancel_scan() -> None:
    S._scan_cancel.set()
    S._scan_pause.clear()
    with S.lock:
        S.scan_status = "idle"


def add_to_tasks(card_ids: list[str]) -> dict:
    r"""
    将源卡片添加到任务栏
    :param: card_ids: 源卡片 ID 列表
    :return: dict
    """
    added: int = 0
    with S.lock:
        existing: set[tuple[str, str]] = {(c.video_path, c.audio_path) for c in S.task_cards}
        for sid in card_ids:
            for sc in S.source_cards:
                if sc.id == sid:
                    key: tuple[str, str] = (sc.video_path, sc.audio_path)
                    if key not in existing:
                        S.task_cards.append(sc.clone())
                        existing.add(key)
                        added += 1
                    break
    S.log("info", f"已添加 {added} 个视频到任务栏")
    return {"ok": True, "added": added}


def remove_source_cards(card_ids: list[str]) -> None:
    r"""
    移除指定源卡片
    :param: card_ids: 卡片 ID 列表
    """
    ids: set[str] = set(card_ids)
    with S.lock:
        removed: list[VideoCard] = [c for c in S.source_cards if c.id in ids]
        S.source_cards = [c for c in S.source_cards if c.id not in ids]
        for c in removed:
            S._known_keys.discard(S._dedup_key(c))


def remove_task_cards(card_ids: list[str]) -> None:
    r"""
    移除指定任务卡片
    :param: card_ids: 卡片 ID 列表
    """
    ids: set[str] = set(card_ids)
    with S.lock:
        S.task_cards = [c for c in S.task_cards if c.id not in ids]


def clear_source() -> None:
    with S.lock:
        S.source_cards.clear()
        S._known_keys.clear()
    S.log("info", "源栏已清空")


def clear_tasks() -> None:
    with S.lock:
        S.task_cards = [c for c in S.task_cards if c.status == "exporting"]
    S.log("info", "任务栏已清空 (导出中的任务保留)")


def clear_completed() -> None:
    with S.lock:
        S.completed_cards.clear()
    S.log("info", "完成栏已清空")


def start_export(card_ids: list[str]) -> dict:
    r"""
    开始导出任务
    :param: card_ids: 待导出卡片 ID，为空则导出全部排队中的任务
    :return: dict
    """
    with S.lock:
        if S.export_status == "exporting":
            return {"ok": False, "error": "导出正在进行中"}
    if not card_ids:
        with S.lock:
            card_ids = [c.id for c in S.task_cards if c.status == "queued"]
    if not card_ids:
        return {"ok": False, "error": "没有可导出的任务"}

    S._export_cancel.clear()
    t: threading.Thread = threading.Thread(
        target=_export_thread_fn, args=(card_ids,), daemon=True,
    )
    with S.lock:
        S._export_thread = t
    t.start()
    return {"ok": True}


def cancel_export() -> None:
    S._export_cancel.set()
    S.log("info", "正在取消导出...")


def get_cover_bytes(card_id: str) -> tuple[bytes, str] | None:
    r"""
    根据卡片 id 取出封面字节
    :param: card_id: 卡片 id
    :return: (字节, content-type) 或 None
    """
    with S.lock:
        pool: list[VideoCard] = S.source_cards + S.task_cards + S.completed_cards
        for c in pool:
            if c.id != card_id or not c.cover_path:
                continue
            p: Path = Path(c.cover_path)
            if not p.exists():
                continue
            suffix: str = p.suffix.lower()
            ct: str = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
            try:
                return p.read_bytes(), ct
            except OSError:
                return None
    return None
