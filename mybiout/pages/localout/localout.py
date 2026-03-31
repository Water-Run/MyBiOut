r"""
LocalOut! 本地缓存导出服务层, 负责扫描、解析和导出本地视频缓存

:file: mybiout/pages/localout/localout.py
:author: WaterRun
:time: 2026-03-31
"""

import json
import re
import shutil
import subprocess
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

_QN_MAP: dict[int, str] = {
    127: "8K 超高清", 126: "杜比视界", 125: "HDR 真彩", 120: "4K 超清",
    116: "1080P 60帧", 112: "1080P 高码率", 80: "1080P 高清", 74: "720P 60帧",
    64: "720P 高清", 32: "480P 清晰", 16: "360P 流畅", 6: "240P 极速",
}

_AUDIO_CODEC_THRESHOLD: int = 30200


def _uid() -> str:
    r"""
    生成 12 位唯一标识
    :return: str: UUID 前 12 位
    """
    return uuid.uuid4().hex[:12]


def _ts() -> str:
    r"""
    获取当前时间短格式
    :return: str: HH:MM:SS
    """
    return datetime.now().strftime("%H:%M:%S")


def _ts_full() -> str:
    r"""
    获取当前时间完整格式
    :return: str: YYYY-MM-DD HH:MM:SS
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _sanitize(name: str) -> str:
    r"""
    清理文件名中的非法字符
    :param: name: 原始名称
    :return: str: 安全的文件名
    """
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")
    return name[:200] if name else "untitled"


def _size_mb(b: int | float) -> float:
    r"""
    将字节数转换为 MB
    :param: b: 字节数
    :return: float: MB 值
    """
    return round(b / 1048576, 1) if b else 0


def _run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    r"""
    执行外部命令
    :param: cmd: 命令参数列表
    :param: timeout: 超时秒数
    :return: subprocess.CompletedProcess: 命令执行结果
    """
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _has_adb() -> bool:
    r"""
    检测 ADB 是否可用
    :return: bool: 是否可用
    """
    try:
        _run(["adb", "version"], timeout=5)
        return True
    except Exception:
        return False


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
    status: str = "queued"
    error: str = ""

    def __post_init__(self) -> None:
        r"""
        初始化后类型强制转换
        """
        self.avid = str(self.avid)
        self.part = int(self.part)
        self.size_bytes = int(self.size_bytes)

    def to_dict(self) -> dict:
        r"""
        转换为前端可用的字典
        :return: dict: 卡片字典
        """
        return {
            "id": self.id, "title": self.title, "bvid": self.bvid, "avid": self.avid,
            "up_name": self.up_name, "group_title": self.group_title, "part": self.part,
            "quality": self.quality, "resolution": self.resolution, "size_bytes": self.size_bytes,
            "size_mb": _size_mb(self.size_bytes), "publish_time": self.publish_time,
            "folder_name": self.folder_name, "source_label": self.source_label,
            "source_type": self.source_type, "status": self.status, "error": self.error,
        }

    def clone(self) -> "VideoCard":
        r"""
        克隆卡片, 生成新 ID 并重置状态
        :return: VideoCard: 新的卡片副本
        """
        return replace(self, id=_uid(), status="queued", error="")


class _State:
    r"""
    LocalOut 全局运行状态管理
    """

    def __init__(self) -> None:
        r"""
        初始化全局状态
        """
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

    def log(self, level: str, msg: str) -> None:
        r"""
        记录日志
        :param: level: 日志级别
        :param: msg: 日志消息
        """
        with self.lock:
            self.logs.append({"time": _ts(), "level": level, "msg": msg})
            if len(self.logs) > 500:
                self.logs = self.logs[-300:]

    def snapshot(self) -> dict:
        r"""
        获取当前状态快照
        :return: dict: 状态数据
        """
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
        r"""
        生成去重键
        :param: c: 视频卡片
        :return: str: 去重键
        """
        return f"{c.source_type}|{c.video_path}|{c.audio_path}"

    def add_source_card(self, c: VideoCard) -> bool:
        r"""
        添加源卡片, 自动去重
        :param: c: 视频卡片
        :return: bool: 是否成功添加
        """
        k: str = self._dedup_key(c)
        with self.lock:
            if k in self._known_keys:
                return False
            self._known_keys.add(k)
            self.source_cards.append(c)
            return True


S: _State = _State()


def _parse_entry_json(path: Path, source_label: str, source_type: str, serial: str = "") -> VideoCard | None:
    r"""
    解析安卓缓存 entry.json 文件
    :param: path: entry.json 路径
    :param: source_label: 来源标签
    :param: source_type: 来源类型
    :param: serial: 设备序列号
    :return: VideoCard | None: 解析成功返回卡片, 否则 None
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

    if type_tag and (quality_dir := parent_dir / type_tag).is_dir():
        if (vp := quality_dir / "video.m4s").exists():
            video_path = str(vp)
        if (ap := quality_dir / "audio.m4s").exists():
            audio_path = str(ap)

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
    )


def _parse_index_json_fallback(quality_dir: Path, source_label: str, source_type: str) -> VideoCard | None:
    r"""
    entry.json 不存在时用 index.json 作为降级解析
    :param: quality_dir: 画质子目录
    :param: source_label: 来源标签
    :param: source_type: 来源类型
    :return: VideoCard | None: 解析成功返回卡片, 否则 None
    """
    if not (quality_dir / "index.json").exists():
        return None
    if not (vp := quality_dir / "video.m4s").exists():
        return None

    parent: Path = quality_dir.parent
    grandparent: Path = parent.parent

    return VideoCard(
        quality=quality_dir.name,
        folder_name=grandparent.name if grandparent else parent.name,
        source_label=source_label, source_type=source_type,
        video_path=str(vp),
        audio_path=str(ap) if (ap := quality_dir / "audio.m4s").exists() else "",
    )


def _find_pc_m4s(cache_dir: Path) -> tuple[str, str]:
    r"""
    在 PC 缓存目录中查找 video 和 audio m4s 文件
    :param: cache_dir: 缓存子目录
    :return: tuple[str, str]: (视频路径, 音频路径)
    """
    video: str = ""
    audio: str = ""
    for f in cache_dir.iterdir():
        if f.suffix == ".m4s" and f.is_file():
            parts: list[str] = f.stem.split("-")
            if len(parts) >= 3:
                try:
                    codec_id: int = int(parts[-1])
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
    :return: VideoCard | None: 解析成功返回卡片, 否则 None
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
            ...

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
    )


def _scan_local_dir(root: Path, source_label: str) -> list[VideoCard]:
    r"""
    自动检测并扫描本地目录中的缓存
    :param: root: 根目录
    :param: source_label: 来源标签
    :return: list[VideoCard]: 扫描到的卡片列表
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

    if not cards and not entry_files and not vi_files:
        for sub in root.iterdir():
            if sub.is_dir():
                for qd in sub.iterdir():
                    if qd.is_dir() and (qd / "video.m4s").exists():
                        if (c := _parse_index_json_fallback(qd, source_label, "local")) and S.add_source_card(c):
                            cards.append(c)
    return cards


def _scan_pc_cache(root: Path, source_label: str) -> list[VideoCard]:
    r"""
    扫描 PC 缓存目录
    :param: root: 缓存根目录
    :param: source_label: 来源标签
    :return: list[VideoCard]: 扫描到的卡片列表
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
                )
                if S.add_source_card(c):
                    cards.append(c)

        if total:
            with S.lock:
                S.scan_progress = (i + 1) / total
    return cards


def _scan_adb(serial: str, package: str, source_label: str) -> list[VideoCard]:
    r"""
    通过 ADB 扫描安卓设备上的缓存
    :param: serial: 设备序列号
    :param: package: 应用包名
    :param: source_label: 来源标签
    :return: list[VideoCard]: 扫描到的卡片列表
    """
    cards: list[VideoCard] = []
    base: str = f"/sdcard/Android/data/{package}/files/download"

    try:
        r: subprocess.CompletedProcess = _run(
            ["adb", "-s", serial, "shell", f"find {base} -name entry.json 2>/dev/null"], timeout=30,
        )
        if r.returncode != 0 or not r.stdout.strip():
            S.log("warn", f"ADB 无法访问 {base}（建议复制到本地后使用"浏览本地路径"）")
            return cards
    except Exception as e:
        S.log("error", f"ADB 命令失败: {e}")
        return cards

    remote_entries: list[str] = [line.strip() for line in r.stdout.strip().split("\n") if line.strip()]
    total: int = len(remote_entries)
    S.log("info", f"ADB 发现 {total} 个缓存项")

    for i, remote_path in enumerate(remote_entries):
        if S._scan_cancel.is_set():
            break
        while S._scan_pause.is_set() and not S._scan_cancel.is_set():
            time.sleep(0.2)

        try:
            cr: subprocess.CompletedProcess = _run(
                ["adb", "-s", serial, "shell", f"cat '{remote_path}'"], timeout=10,
            )
            if cr.returncode != 0:
                continue
            data: dict = json.loads(cr.stdout)
        except Exception:
            continue

        page_data: dict = data.get("page_data") or {}
        w: int = page_data.get("width", 0)
        h: int = page_data.get("height", 0)
        type_tag: str = str(data.get("type_tag", ""))
        remote_dir: str = remote_path.rsplit("/", 1)[0]

        c: VideoCard = VideoCard(
            title=data.get("title", ""), bvid=data.get("bvid", "") or "",
            avid=str(data.get("avid", "")), up_name=data.get("owner_name", ""),
            part=page_data.get("page", 1), quality=data.get("quality_pithy_description", ""),
            resolution=f"{w}×{h}" if w and h else "",
            size_bytes=data.get("total_bytes", 0),
            folder_name=remote_dir.rsplit("/", 1)[-1],
            source_label=source_label, source_type="android_adb", device_serial=serial,
            video_path=f"{remote_dir}/{type_tag}/video.m4s",
            audio_path=f"{remote_dir}/{type_tag}/audio.m4s",
        )
        if S.add_source_card(c):
            cards.append(c)
        if total:
            with S.lock:
                S.scan_progress = (i + 1) / total
    return cards


def _scan_thread_fn(source_type: str, path: str, label: str, serial: str, package: str) -> None:
    r"""
    扫描线程入口函数
    :param: source_type: 来源类型
    :param: path: 扫描路径
    :param: label: 来源标签
    :param: serial: 设备序列号
    :param: package: 应用包名
    """
    try:
        S.log("info", f"开始扫描: {label}")
        with S.lock:
            S.scan_status = "scanning"
            S.scan_progress = 0.0

        match source_type:
            case "pc":
                found = _scan_pc_cache(Path(path), label)
            case "android_adb":
                found = _scan_adb(serial, package, label)
            case _:
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


def _build_filename(card: VideoCard) -> str:
    r"""
    按设置中的 name_parts 组合导出文件名
    :param: card: 视频卡片
    :return: str: 组合后的文件名, 为空表示应跳过
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


def _export_single(card: VideoCard, output_dir: Path) -> None:
    r"""
    导出单个视频
    :param: card: 视频卡片
    :param: output_dir: 输出目录
    :raise: RuntimeError: biliffm4s 未安装或标题不完整且策略为跳过
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

    if card.source_type == "android_adb":
        _adb_pull_and_combine(card, str(output))
    else:
        _local_combine(card, str(output))


def _local_combine(card: VideoCard, output: str) -> None:
    r"""
    本地文件合并
    :param: card: 视频卡片
    :param: output: 输出路径
    :raise: FileNotFoundError: 视频文件不存在
    """
    vp: str = card.video_path
    ap: str = card.audio_path
    if not vp or not Path(vp).exists():
        raise FileNotFoundError(f"视频文件不存在: {vp}")
    if ap and not Path(ap).exists():
        ap = ""
    _ffm4s.combine(vp, ap if ap else vp, output)


def _adb_pull_and_combine(card: VideoCard, output: str) -> None:
    r"""
    通过 ADB 拉取文件后合并
    :param: card: 视频卡片
    :param: output: 输出路径
    :raise: RuntimeError: ADB pull 失败
    """
    tmp_dir: Path = Path(tempfile.mkdtemp(prefix="mybiout_adb_"))
    try:
        local_v: Path = tmp_dir / "video.m4s"
        local_a: Path = tmp_dir / "audio.m4s"

        rv: subprocess.CompletedProcess = _run(
            ["adb", "-s", card.device_serial, "pull", card.video_path, str(local_v)], timeout=120,
        )
        if rv.returncode != 0:
            raise RuntimeError(f"ADB pull video 失败: {rv.stderr.strip()}")

        has_audio: bool = False
        if card.audio_path:
            ra: subprocess.CompletedProcess = _run(
                ["adb", "-s", card.device_serial, "pull", card.audio_path, str(local_a)], timeout=120,
            )
            has_audio = ra.returncode == 0 and local_a.exists()

        _ffm4s.combine(str(local_v), str(local_a) if has_audio else str(local_v), output)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
        r"""
        导出单个卡片的线程任务
        :param: card: 视频卡片
        """
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


def get_state() -> dict:
    r"""
    获取当前状态快照
    :return: dict: 状态数据
    """
    return S.snapshot()


def get_available_sources() -> list[dict]:
    r"""
    获取可用的扫描源列表
    :return: list[dict]: 可用源
    """
    sources: list[dict] = [{"id": "browse", "label": "浏览本地路径...", "type": "browse"}]

    pc_path: str = utils.get_setting("localout", "bilibili_pc_cache_path").strip()
    if pc_path:
        optional: bool = utils.get_setting("localout", "bilibili_pc_cache_optional_when_installed") == "true"
        if not (optional and not Path(pc_path).is_dir()):
            sources.append({"id": "pc_cache", "label": "哔哩哔哩桌面端缓存", "type": "pc", "path": pc_path})

    if utils.get_setting("localout", "scan_android") == "true" and _has_adb():
        try:
            r: subprocess.CompletedProcess = _run(["adb", "devices", "-l"], timeout=8)
            for line in r.stdout.strip().split("\n")[1:]:
                if not line.strip() or "offline" in line or "unauthorized" in line:
                    continue
                line_parts: list[str] = line.split()
                if len(line_parts) >= 2 and line_parts[1] == "device":
                    serial: str = line_parts[0]
                    model: str = next(
                        (p[6:].replace("_", " ") for p in line_parts[2:] if p.startswith("model:")),
                        serial,
                    )
                    for pkg, name in _BILI_PACKAGES:
                        try:
                            cr: subprocess.CompletedProcess = _run(
                                ["adb", "-s", serial, "shell",
                                 f"ls /sdcard/Android/data/{pkg}/files/download/ 2>/dev/null"],
                                timeout=8,
                            )
                            if cr.returncode == 0 and cr.stdout.strip():
                                sources.append({
                                    "id": f"adb_{serial}_{pkg}", "label": f"{model} — {name}",
                                    "type": "android_adb", "serial": serial, "package": pkg,
                                })
                        except Exception:
                            ...
        except Exception:
            ...
    return sources


def browse_local() -> str | None:
    r"""
    弹出文件夹对话框选择本地缓存目录
    :return: str | None: 选中的路径, 取消时返回 None
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


def add_source(source_type: str, path: str = "", label: str = "", serial: str = "", package: str = "") -> dict:
    r"""
    添加扫描源并启动扫描
    :param: source_type: 来源类型
    :param: path: 扫描路径
    :param: label: 来源标签
    :param: serial: 设备序列号
    :param: package: 应用包名
    :return: dict: 添加结果
    """
    with S.lock:
        if S.scan_status == "scanning":
            return {"ok": False, "error": "已有扫描在进行中"}

    S._scan_cancel.clear()
    S._scan_pause.clear()
    t: threading.Thread = threading.Thread(
        target=_scan_thread_fn, args=(source_type, path, label or path or source_type, serial, package), daemon=True,
    )
    with S.lock:
        S._scan_thread = t
    t.start()
    return {"ok": True}


def pause_scan() -> None:
    r"""
    暂停当前扫描
    """
    S._scan_pause.set()
    with S.lock:
        if S.scan_status == "scanning":
            S.scan_status = "paused"
    S.log("info", "扫描已暂停")


def resume_scan() -> None:
    r"""
    恢复暂停的扫描
    """
    S._scan_pause.clear()
    with S.lock:
        if S.scan_status == "paused":
            S.scan_status = "scanning"
    S.log("info", "扫描已继续")


def cancel_scan() -> None:
    r"""
    取消当前扫描
    """
    S._scan_cancel.set()
    S._scan_pause.clear()
    with S.lock:
        S.scan_status = "idle"


def add_to_tasks(card_ids: list[str]) -> dict:
    r"""
    将源卡片添加到任务栏
    :param: card_ids: 源卡片 ID 列表
    :return: dict: 添加结果
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
    r"""
    清空源栏
    """
    with S.lock:
        S.source_cards.clear()
        S._known_keys.clear()
    S.log("info", "源栏已清空")


def clear_tasks() -> None:
    r"""
    清空任务栏, 保留导出中的任务
    """
    with S.lock:
        S.task_cards = [c for c in S.task_cards if c.status == "exporting"]
    S.log("info", "任务栏已清空 (导出中的任务保留)")


def clear_completed() -> None:
    r"""
    清空完成栏
    """
    with S.lock:
        S.completed_cards.clear()
    S.log("info", "完成栏已清空")


def start_export(card_ids: list[str]) -> dict:
    r"""
    开始导出任务
    :param: card_ids: 待导出的卡片 ID 列表, 为空则导出全部排队中的任务
    :return: dict: 导出结果
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
    t: threading.Thread = threading.Thread(target=_export_thread_fn, args=(card_ids,), daemon=True)
    with S.lock:
        S._export_thread = t
    t.start()
    return {"ok": True}


def cancel_export() -> None:
    r"""
    取消正在进行的导出
    """
    S._export_cancel.set()
    S.log("info", "正在取消导出...")
    