"""LocalOut! — 本地缓存导出 服务层"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from mybiout.pages import utils

# ============================== ffm4s ==============================

try:
    from biliffm4s import biliffm4s as _ffm4s

    _HAS_FFM4S = True
except Exception:
    _ffm4s = None
    _HAS_FFM4S = False

# ============================== 常量 ==============================

_BILI_PACKAGES = [
    ("tv.danmaku.bili", "哔哩哔哩"),
    ("com.bilibili.app.blue", "哔哩哔哩概念版"),
    ("com.bilibili.app.in", "哔哩哔哩国际版"),
]

_QN_MAP = {
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

_AUDIO_CODEC_THRESHOLD = 30200


# ============================== 工具 ==============================


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _ts_full() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(". ")
    return name[:200] if name else "untitled"


def _size_mb(b: int | float) -> float:
    return round(b / 1048576, 1) if b else 0


def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _has_adb() -> bool:
    try:
        _run(["adb", "version"], timeout=5)
        return True
    except Exception:
        return False


# ============================== VideoCard ==============================


class VideoCard:
    __slots__ = (
        "id",
        "title",
        "bvid",
        "avid",
        "up_name",
        "group_title",
        "part",
        "quality",
        "resolution",
        "size_bytes",
        "publish_time",
        "folder_name",
        "source_label",
        "source_type",
        "device_serial",
        "video_path",
        "audio_path",
        "status",
        "error",
    )

    def __init__(self, **kw):
        self.id: str = kw.get("id", _uid())
        self.title: str = kw.get("title", "")
        self.bvid: str = kw.get("bvid", "")
        self.avid: str = str(kw.get("avid", ""))
        self.up_name: str = kw.get("up_name", "")
        self.group_title: str = kw.get("group_title", "")
        self.part: int = int(kw.get("part", 1))
        self.quality: str = kw.get("quality", "")
        self.resolution: str = kw.get("resolution", "")
        self.size_bytes: int = int(kw.get("size_bytes", 0))
        self.publish_time: str = kw.get("publish_time", "")
        self.folder_name: str = kw.get("folder_name", "")
        self.source_label: str = kw.get("source_label", "")
        self.source_type: str = kw.get("source_type", "")
        self.device_serial: str = kw.get("device_serial", "")
        self.video_path: str = kw.get("video_path", "")
        self.audio_path: str = kw.get("audio_path", "")
        self.status: str = kw.get("status", "queued")
        self.error: str = kw.get("error", "")

    def to_dict(self) -> dict:
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
            "size_mb": _size_mb(self.size_bytes),
            "publish_time": self.publish_time,
            "folder_name": self.folder_name,
            "source_label": self.source_label,
            "source_type": self.source_type,
            "status": self.status,
            "error": self.error,
        }

    def clone(self) -> "VideoCard":
        c = VideoCard()
        for s in self.__slots__:
            setattr(c, s, getattr(self, s))
        c.id = _uid()
        c.status = "queued"
        c.error = ""
        return c


# ============================== 全局状态 ==============================


class _State:
    def __init__(self):
        self.lock = threading.RLock()
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
        self._scan_cancel = threading.Event()
        self._scan_pause = threading.Event()
        self._export_thread: threading.Thread | None = None
        self._export_cancel = threading.Event()
        self._known_keys: set[str] = set()

    def log(self, level: str, msg: str):
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
                "scan_status": self.scan_status,
                "scan_progress": round(self.scan_progress, 3),
                "export_status": self.export_status,
                "export_progress": round(self.export_progress, 3),
                "export_total": self.export_total,
                "export_done": self.export_done,
            }

    def _dedup_key(self, c: VideoCard) -> str:
        return f"{c.source_type}|{c.video_path}|{c.audio_path}"

    def add_source_card(self, c: VideoCard) -> bool:
        k = self._dedup_key(c)
        with self.lock:
            if k in self._known_keys:
                return False
            self._known_keys.add(k)
            self.source_cards.append(c)
            return True


S = _State()


# ============================== 解析器 ==============================


def _parse_entry_json(path: Path, source_label: str, source_type: str, serial: str = "") -> VideoCard | None:
    """解析安卓缓存 entry.json"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    title = data.get("title", "")
    bvid = data.get("bvid", "") or ""
    avid = str(data.get("avid", ""))
    up_name = data.get("owner_name", "")
    quality = data.get("quality_pithy_description", "")
    size_bytes = data.get("total_bytes", 0)

    page_data = data.get("page_data") or {}
    part = page_data.get("page", 1)
    w = page_data.get("width", 0)
    h = page_data.get("height", 0)
    resolution = f"{w}×{h}" if w and h else ""

    type_tag = str(data.get("type_tag", ""))
    parent_dir = path.parent
    quality_dir = parent_dir / type_tag if type_tag else None

    video_path = ""
    audio_path = ""
    if quality_dir and quality_dir.is_dir():
        vp = quality_dir / "video.m4s"
        ap = quality_dir / "audio.m4s"
        if vp.exists():
            video_path = str(vp)
        if ap.exists():
            audio_path = str(ap)

    if not video_path:
        for sub in parent_dir.iterdir():
            if sub.is_dir():
                vp = sub / "video.m4s"
                ap = sub / "audio.m4s"
                if vp.exists():
                    video_path = str(vp)
                if ap.exists():
                    audio_path = str(ap)
                if video_path:
                    break

    if not video_path:
        return None

    return VideoCard(
        title=title,
        bvid=bvid,
        avid=avid,
        up_name=up_name,
        group_title="",
        part=part,
        quality=quality,
        resolution=resolution,
        size_bytes=size_bytes,
        folder_name=parent_dir.name,
        source_label=source_label,
        source_type=source_type,
        device_serial=serial,
        video_path=video_path,
        audio_path=audio_path,
    )


def _parse_index_json_fallback(quality_dir: Path, source_label: str, source_type: str) -> VideoCard | None:
    """当 entry.json 不存在时用 index.json 作为降级"""
    idx = quality_dir / "index.json"
    if not idx.exists():
        return None

    vp = quality_dir / "video.m4s"
    ap = quality_dir / "audio.m4s"
    if not vp.exists():
        return None

    try:
        data = json.loads(idx.read_text(encoding="utf-8"))
    except Exception:
        data = {}

    parent = quality_dir.parent
    grandparent = parent.parent

    return VideoCard(
        title="",
        bvid="",
        avid="",
        up_name="",
        quality=quality_dir.name,
        folder_name=grandparent.name if grandparent else parent.name,
        source_label=source_label,
        source_type=source_type,
        video_path=str(vp),
        audio_path=str(ap) if ap.exists() else "",
    )


def _parse_video_info_json(path: Path, source_label: str) -> VideoCard | None:
    """解析 PC 缓存 videoInfo.json"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    title = data.get("title", "") or data.get("groupTitle", "")
    bvid = data.get("bvid", "") or ""
    avid = str(data.get("aid", "") or "")
    up_name = data.get("uname", "")
    group_title = data.get("groupTitle", "") or ""
    part = data.get("p", 1)
    qn = data.get("qn", 0)
    quality = _QN_MAP.get(qn, str(qn) if qn else "")
    size_bytes = data.get("totalSize", 0)

    pubdate = data.get("pubdate", 0)
    publish_time = ""
    if pubdate:
        try:
            publish_time = datetime.fromtimestamp(pubdate).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

    cache_dir = path.parent
    video_path, audio_path = _find_pc_m4s(cache_dir)

    if not video_path:
        return None

    return VideoCard(
        title=title,
        bvid=bvid,
        avid=avid,
        up_name=up_name,
        group_title=group_title,
        part=part,
        quality=quality,
        size_bytes=size_bytes,
        publish_time=publish_time,
        folder_name=cache_dir.name,
        source_label=source_label,
        source_type="pc",
        video_path=video_path,
        audio_path=audio_path,
    )


def _find_pc_m4s(cache_dir: Path) -> tuple[str, str]:
    """在 PC 缓存目录中找到 video 和 audio m4s"""
    video, audio = "", ""
    for f in cache_dir.iterdir():
        if f.suffix == ".m4s" and f.is_file():
            parts = f.stem.split("-")
            if len(parts) >= 3:
                try:
                    codec_id = int(parts[-1])
                    if codec_id >= _AUDIO_CODEC_THRESHOLD:
                        audio = str(f)
                    else:
                        video = str(f)
                except ValueError:
                    if not video:
                        video = str(f)
            else:
                if not video:
                    video = str(f)
    return video, audio


# ============================== 扫描器 ==============================


def _scan_local_dir(root: Path, source_label: str) -> list[VideoCard]:
    """自动检测并扫描本地目录 (安卓风格 / PC 风格)"""
    cards: list[VideoCard] = []

    entry_files = list(root.rglob("entry.json"))
    vi_files = list(root.rglob("videoInfo.json"))
    total = len(entry_files) + len(vi_files)

    for i, ef in enumerate(entry_files):
        if S._scan_cancel.is_set():
            break
        while S._scan_pause.is_set() and not S._scan_cancel.is_set():
            time.sleep(0.2)
        c = _parse_entry_json(ef, source_label, "local")
        if c and S.add_source_card(c):
            cards.append(c)
        if total:
            with S.lock:
                S.scan_progress = (i + 1) / total

    for i, vf in enumerate(vi_files):
        if S._scan_cancel.is_set():
            break
        while S._scan_pause.is_set() and not S._scan_cancel.is_set():
            time.sleep(0.2)
        c = _parse_video_info_json(vf, source_label)
        if c and S.add_source_card(c):
            cards.append(c)
        if total:
            with S.lock:
                S.scan_progress = (len(entry_files) + i + 1) / total

    if not cards and not entry_files and not vi_files:
        for sub in root.iterdir():
            if sub.is_dir():
                for qd in sub.iterdir():
                    if qd.is_dir() and (qd / "video.m4s").exists():
                        c = _parse_index_json_fallback(qd, source_label, "local")
                        if c and S.add_source_card(c):
                            cards.append(c)

    return cards


def _scan_pc_cache(root: Path, source_label: str) -> list[VideoCard]:
    """扫描 PC 缓存目录"""
    cards: list[VideoCard] = []
    if not root.is_dir():
        S.log("error", f"PC 缓存路径不存在: {root}")
        return cards

    subdirs = [d for d in root.iterdir() if d.is_dir()]
    total = len(subdirs)

    for i, sd in enumerate(subdirs):
        if S._scan_cancel.is_set():
            break
        while S._scan_pause.is_set() and not S._scan_cancel.is_set():
            time.sleep(0.2)

        vf = sd / "videoInfo.json"
        if vf.exists():
            c = _parse_video_info_json(vf, source_label)
            if c and S.add_source_card(c):
                cards.append(c)
        else:
            video, audio = _find_pc_m4s(sd)
            if video:
                c = VideoCard(
                    folder_name=sd.name,
                    source_label=source_label,
                    source_type="pc",
                    video_path=video,
                    audio_path=audio,
                )
                if S.add_source_card(c):
                    cards.append(c)

        if total:
            with S.lock:
                S.scan_progress = (i + 1) / total

    return cards


def _scan_adb(serial: str, package: str, source_label: str) -> list[VideoCard]:
    """通过 ADB 扫描安卓设备"""
    cards: list[VideoCard] = []
    base = f"/sdcard/Android/data/{package}/files/download"

    try:
        r = _run(["adb", "-s", serial, "shell", f"find {base} -name entry.json 2>/dev/null"], timeout=30)
        if r.returncode != 0 or not r.stdout.strip():
            S.log("warn", f"ADB 无法访问 {base}（可能受 Android 作用域存储限制，建议复制到本地后使用"浏览本地路径"）")
            return cards
    except Exception as e:
        S.log("error", f"ADB 命令失败: {e}")
        return cards

    remote_entries = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
    total = len(remote_entries)
    S.log("info", f"ADB 发现 {total} 个缓存项")

    for i, remote_path in enumerate(remote_entries):
        if S._scan_cancel.is_set():
            break
        while S._scan_pause.is_set() and not S._scan_cancel.is_set():
            time.sleep(0.2)

        try:
            cr = _run(["adb", "-s", serial, "shell", f"cat '{remote_path}'"], timeout=10)
            if cr.returncode != 0:
                continue
            data = json.loads(cr.stdout)
        except Exception:
            continue

        title = data.get("title", "")
        bvid = data.get("bvid", "") or ""
        avid = str(data.get("avid", ""))
        up_name = data.get("owner_name", "")
        quality = data.get("quality_pithy_description", "")
        size_bytes = data.get("total_bytes", 0)
        type_tag = str(data.get("type_tag", ""))
        page_data = data.get("page_data") or {}
        part = page_data.get("page", 1)
        w = page_data.get("width", 0)
        h = page_data.get("height", 0)
        resolution = f"{w}×{h}" if w and h else ""

        remote_dir = remote_path.rsplit("/", 1)[0]
        remote_video = f"{remote_dir}/{type_tag}/video.m4s"
        remote_audio = f"{remote_dir}/{type_tag}/audio.m4s"

        c = VideoCard(
            title=title,
            bvid=bvid,
            avid=avid,
            up_name=up_name,
            part=part,
            quality=quality,
            resolution=resolution,
            size_bytes=size_bytes,
            folder_name=remote_dir.rsplit("/", 1)[-1],
            source_label=source_label,
            source_type="android_adb",
            device_serial=serial,
            video_path=remote_video,
            audio_path=remote_audio,
        )
        if S.add_source_card(c):
            cards.append(c)

        if total:
            with S.lock:
                S.scan_progress = (i + 1) / total

    return cards


def _scan_thread_fn(source_type: str, path: str, label: str, serial: str, package: str):
    try:
        S.log("info", f"开始扫描: {label}")
        with S.lock:
            S.scan_status = "scanning"
            S.scan_progress = 0.0

        if source_type == "pc":
            found = _scan_pc_cache(Path(path), label)
        elif source_type == "android_adb":
            found = _scan_adb(serial, package, label)
        else:
            found = _scan_local_dir(Path(path), label)

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


# ============================== 导出器 ==============================


def _build_filename(card: VideoCard) -> str:
    """按设置中的 name_parts 组合文件名"""
    raw = utils.get_setting("localout", "name_parts")
    parts = set(raw.split(","))
    action = utils.get_setting("localout", "incomplete_title_action")

    display_title = card.title
    if not display_title:
        if action == "skip":
            return ""
        if action == "folder_only":
            display_title = card.folder_name or "untitled"
        else:
            display_title = card.folder_name or "untitled"

    segs: list[str] = []
    if "up" in parts and card.up_name:
        segs.append(card.up_name)

    mid = ""
    if "bv" in parts:
        bv = card.bvid or (f"av{card.avid}" if card.avid else "")
        if bv:
            mid += f"{{{bv}}}"
    gp = ""
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

    main = "--".join(segs) if segs else "untitled"

    tails: list[str] = []
    if "publish_time" in parts and card.publish_time:
        tails.append(card.publish_time)
    if "export_time" in parts:
        tails.append(f"导出于{_ts_full()}")
    if tails:
        main += "--" + ",".join(tails)

    return _sanitize(main) + ".mp4"


def _export_single(card: VideoCard, output_dir: Path):
    """导出单个视频"""
    if not _HAS_FFM4S:
        raise RuntimeError("biliffm4s 未安装")

    fname = _build_filename(card)
    if not fname:
        raise RuntimeError("标题不完整且策略为跳过")

    output = output_dir / fname
    counter = 1
    while output.exists():
        stem = output.stem
        output = output_dir / f"{stem}_{counter}.mp4"
        counter += 1

    if card.source_type == "android_adb":
        _adb_pull_and_combine(card, str(output))
    else:
        _local_combine(card, str(output))


def _local_combine(card: VideoCard, output: str):
    vp = card.video_path
    ap = card.audio_path
    if not vp or not Path(vp).exists():
        raise FileNotFoundError(f"视频文件不存在: {vp}")
    if ap and not Path(ap).exists():
        ap = ""
    _ffm4s.combine(vp, ap, output) if ap else _ffm4s.combine(vp, vp, output)


def _adb_pull_and_combine(card: VideoCard, output: str):
    tmp = tempfile.mkdtemp(prefix="mybiout_adb_")
    try:
        local_v = os.path.join(tmp, "video.m4s")
        local_a = os.path.join(tmp, "audio.m4s")

        rv = _run(["adb", "-s", card.device_serial, "pull", card.video_path, local_v], timeout=120)
        if rv.returncode != 0:
            raise RuntimeError(f"ADB pull video 失败: {rv.stderr.strip()}")

        if card.audio_path:
            ra = _run(["adb", "-s", card.device_serial, "pull", card.audio_path, local_a], timeout=120)
            if ra.returncode != 0:
                local_a = ""

        if local_a and os.path.exists(local_a):
            _ffm4s.combine(local_v, local_a, output)
        else:
            _ffm4s.combine(local_v, local_v, output)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _export_thread_fn(card_ids: list[str]):
    export_root = utils.get_export_path()
    folder = utils.get_setting("localout", "folder")
    output_dir = export_root / folder
    output_dir.mkdir(parents=True, exist_ok=True)

    concurrent = int(utils.get_setting("localout", "ffmpeg_concurrent") or "3")
    concurrent = max(1, min(concurrent, 32))

    with S.lock:
        targets = [c for c in S.task_cards if c.id in card_ids]
        S.export_total = len(targets)
        S.export_done = 0
        S.export_progress = 0.0
        S.export_status = "exporting"

    S.log("info", f"开始导出 {len(targets)} 个视频 (并发 {concurrent})")

    def _do_one(card: VideoCard):
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
        futs = {pool.submit(_do_one, c): c for c in targets}
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


# ============================== 公共 API ==============================


def get_state() -> dict:
    return S.snapshot()


def get_available_sources() -> list[dict]:
    sources: list[dict] = [
        {"id": "browse", "label": "浏览本地路径...", "type": "browse"},
    ]

    pc_path = utils.get_setting("localout", "bilibili_pc_cache_path").strip()
    if pc_path:
        optional = utils.get_setting("localout", "bilibili_pc_cache_optional_when_installed") == "true"
        show = True
        if optional and not Path(pc_path).is_dir():
            show = False
        if show:
            sources.append({
                "id": "pc_cache",
                "label": "哔哩哔哩桌面端缓存",
                "type": "pc",
                "path": pc_path,
            })

    scan_android = utils.get_setting("localout", "scan_android") == "true"
    if scan_android and _has_adb():
        try:
            r = _run(["adb", "devices", "-l"], timeout=8)
            for line in r.stdout.strip().split("\n")[1:]:
                if not line.strip() or "offline" in line or "unauthorized" in line:
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    serial = parts[0]
                    model = serial
                    for p in parts[2:]:
                        if p.startswith("model:"):
                            model = p[6:].replace("_", " ")
                            break
                    for pkg, name in _BILI_PACKAGES:
                        try:
                            cr = _run(
                                ["adb", "-s", serial, "shell", f"ls /sdcard/Android/data/{pkg}/files/download/ 2>/dev/null"],
                                timeout=8,
                            )
                            if cr.returncode == 0 and cr.stdout.strip():
                                sources.append({
                                    "id": f"adb_{serial}_{pkg}",
                                    "label": f"{model} — {name}",
                                    "type": "android_adb",
                                    "serial": serial,
                                    "package": pkg,
                                })
                        except Exception:
                            pass
        except Exception:
            pass

    return sources


def browse_local() -> str | None:
    try:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="选择缓存目录")
        root.destroy()
        return folder if folder else None
    except Exception:
        return None


def add_source(source_type: str, path: str = "", label: str = "", serial: str = "", package: str = "") -> dict:
    with S.lock:
        if S.scan_status == "scanning":
            return {"ok": False, "error": "已有扫描在进行中"}

    if not label:
        label = path or source_type

    S._scan_cancel.clear()
    S._scan_pause.clear()
    t = threading.Thread(
        target=_scan_thread_fn,
        args=(source_type, path, label, serial, package),
        daemon=True,
    )
    with S.lock:
        S._scan_thread = t
    t.start()
    return {"ok": True}


def pause_scan():
    S._scan_pause.set()
    with S.lock:
        if S.scan_status == "scanning":
            S.scan_status = "paused"
    S.log("info", "扫描已暂停")


def resume_scan():
    S._scan_pause.clear()
    with S.lock:
        if S.scan_status == "paused":
            S.scan_status = "scanning"
    S.log("info", "扫描已继续")


def cancel_scan():
    S._scan_cancel.set()
    S._scan_pause.clear()
    with S.lock:
        S.scan_status = "idle"


def add_to_tasks(card_ids: list[str]) -> dict:
    added = 0
    with S.lock:
        existing = {(c.video_path, c.audio_path) for c in S.task_cards}
        for sid in card_ids:
            for sc in S.source_cards:
                if sc.id == sid:
                    key = (sc.video_path, sc.audio_path)
                    if key not in existing:
                        tc = sc.clone()
                        tc.status = "queued"
                        S.task_cards.append(tc)
                        existing.add(key)
                        added += 1
                    break
    S.log("info", f"已添加 {added} 个视频到任务栏")
    return {"ok": True, "added": added}


def remove_source_cards(card_ids: list[str]):
    ids = set(card_ids)
    with S.lock:
        removed = [c for c in S.source_cards if c.id in ids]
        S.source_cards = [c for c in S.source_cards if c.id not in ids]
        for c in removed:
            S._known_keys.discard(S._dedup_key(c))


def remove_task_cards(card_ids: list[str]):
    ids = set(card_ids)
    with S.lock:
        S.task_cards = [c for c in S.task_cards if c.id not in ids]


def clear_source():
    with S.lock:
        S.source_cards.clear()
        S._known_keys.clear()
    S.log("info", "源栏已清空")


def clear_tasks():
    with S.lock:
        S.task_cards = [c for c in S.task_cards if c.status == "exporting"]
    S.log("info", "任务栏已清空 (导出中的任务保留)")


def clear_completed():
    with S.lock:
        S.completed_cards.clear()
    S.log("info", "完成栏已清空")


def start_export(card_ids: list[str]) -> dict:
    with S.lock:
        if S.export_status == "exporting":
            return {"ok": False, "error": "导出正在进行中"}
    if not card_ids:
        with S.lock:
            card_ids = [c.id for c in S.task_cards if c.status == "queued"]
    if not card_ids:
        return {"ok": False, "error": "没有可导出的任务"}

    S._export_cancel.clear()
    t = threading.Thread(target=_export_thread_fn, args=(card_ids,), daemon=True)
    with S.lock:
        S._export_thread = t
    t.start()
    return {"ok": True}


def cancel_export():
    S._export_cancel.set()
    S.log("info", "正在取消导出...")