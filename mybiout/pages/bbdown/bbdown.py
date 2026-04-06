r"""
BBDown! 可视化封装服务层, 管理 BBDown 下载任务队列

:file: mybiout/pages/bbdown/bbdown.py
:author: WaterRun
:time: 2026-04-06
"""

import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from mybiout.pages import utils

_BIN_DIR: Path = Path(__file__).resolve().parent.parent.parent / "bin"
_ANSI_RE: re.Pattern[str] = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_POPEN_EXTRA: dict[str, int] = {}
if sys.platform == "win32":
    _POPEN_EXTRA["creationflags"] = 0x08000000

_CONSOLE_ENC: str = "gbk" if sys.platform == "win32" else "utf-8"


def _find_bbdown() -> str | None:
    r"""
    查找 BBDown 可执行文件
    :return: str | None: 可执行文件路径, 未找到返回 None
    """
    candidates: list[Path] = [
        _BIN_DIR / "BBDown" / "BBDown.exe",
        _BIN_DIR / "BBDown" / "BBDown",
        _BIN_DIR / "BBDown.exe",
        _BIN_DIR / "BBDown",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return shutil.which("BBDown") or shutil.which("bbdown")


def _find_ffmpeg() -> str | None:
    r"""
    查找 ffmpeg 可执行文件
    :return: str | None: 可执行文件路径, 未找到返回 None
    """
    candidates: list[Path] = [
        _BIN_DIR / "BBDown" / "ffmpeg.exe",
        _BIN_DIR / "BBDown" / "ffmpeg",
        _BIN_DIR / "ffmpeg.exe",
        _BIN_DIR / "ffmpeg",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return shutil.which("ffmpeg")


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _ts_full() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(line: str) -> str:
    return _ANSI_RE.sub("", line).strip()


@dataclass(slots=True)
class BBDownTask:
    r"""
    BBDown 下载任务数据模型
    """
    id: str = field(default_factory=_uid)
    url: str = ""
    title: str = ""
    status: str = "queued"
    progress: float = 0.0
    speed: str = ""
    error: str = ""
    options: dict = field(default_factory=dict)
    output_file: str = ""
    output_dir: str = ""
    cover_url: str = ""
    created_at: str = field(default_factory=_ts_full)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title or self.url,
            "status": self.status,
            "progress": round(self.progress, 3),
            "speed": self.speed,
            "error": self.error,
            "options": self.options,
            "output_file": self.output_file,
            "output_dir": self.output_dir,
            "cover_url": self.cover_url,
            "created_at": self.created_at,
        }


class _State:
    def __init__(self) -> None:
        self.lock: threading.RLock = threading.RLock()
        self.tasks: list[BBDownTask] = []
        self.completed: list[BBDownTask] = []
        self.logs: list[dict] = []
        self._worker: threading.Thread | None = None
        self._cancel: threading.Event = threading.Event()
        self._process: subprocess.Popen | None = None

    def log(self, level: str, msg: str) -> None:
        with self.lock:
            self.logs.append({"time": _ts(), "level": level, "msg": msg})
            if len(self.logs) > 500:
                self.logs = self.logs[-300:]

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "tasks": [t.to_dict() for t in self.tasks],
                "completed": [t.to_dict() for t in self.completed],
                "logs": list(self.logs),
                "is_downloading": any(t.status == "downloading" for t in self.tasks),
            }


S: _State = _State()


def _get_work_dir() -> Path:
    work_dir: Path = utils.get_export_path() / utils.get_setting("bbdown", "folder")
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def _build_command(task: BBDownTask) -> list[str]:
    bbdown: str | None = _find_bbdown()
    if not bbdown:
        raise RuntimeError("BBDown 可执行文件未找到")

    cmd: list[str] = [bbdown]
    opts: dict = task.options or {}

    sessdata: str = utils.get_sessdata().strip()
    if sessdata:
        cmd.extend(["-c", f"SESSDATA={sessdata}"])

    match opts.get("api_mode", "default"):
        case "tv":
            cmd.append("-tv")
        case "app":
            cmd.append("-app")
        case "intl":
            cmd.append("-intl")

    quality: str = (opts.get("quality", "") or utils.get_setting("bbdown", "quality_priority")).strip()
    if quality:
        cmd.extend(["-q", quality])

    encoding: str = (opts.get("encoding", "") or utils.get_setting("bbdown", "encoding_priority")).strip()
    if encoding:
        cmd.extend(["-e", encoding])

    content: str = opts.get("content", "default")
    match content:
        case "audio_only":
            cmd.append("--audio-only")
        case "video_only":
            cmd.append("--video-only")
        case "danmaku_only":
            cmd.append("--danmaku-only")
        case "sub_only":
            cmd.append("--sub-only")
        case "cover_only":
            cmd.append("--cover-only")

    want_danmaku: bool = opts.get("download_danmaku", False) or utils.get_setting("bbdown", "download_danmaku") == "true"
    if want_danmaku and content == "default":
        cmd.append("-dd")

    want_skip_sub: bool = opts.get("skip_subtitle", False) or utils.get_setting("bbdown", "skip_subtitle") == "true"
    if want_skip_sub:
        cmd.append("--skip-subtitle")

    want_skip_cover: bool = opts.get("skip_cover", False) or utils.get_setting("bbdown", "skip_cover") == "true"
    if want_skip_cover:
        cmd.append("--skip-cover")

    page: str = opts.get("page", "").strip()
    if page:
        cmd.extend(["-p", page])

    file_pattern: str = utils.get_setting("bbdown", "file_pattern").strip()
    if file_pattern:
        cmd.extend(["-F", file_pattern])

    multi_file_pattern: str = utils.get_setting("bbdown", "multi_file_pattern").strip()
    if multi_file_pattern:
        cmd.extend(["-M", multi_file_pattern])

    work_dir: Path = _get_work_dir()
    cmd.extend(["--work-dir", str(work_dir)])

    if utils.get_setting("bbdown", "use_aria2c") == "true":
        cmd.append("--use-aria2c")

    if ffmpeg := _find_ffmpeg():
        cmd.extend(["--ffmpeg-path", ffmpeg])

    cmd.append(task.url)
    return cmd


def _parse_progress(line: str) -> tuple[float | None, str | None]:
    prog: float | None = None
    speed: str | None = None
    if m := re.search(r"(\d+\.?\d*)%", line):
        prog = min(float(m.group(1)) / 100.0, 1.0)
    if m := re.search(r"(\d+\.?\d*\s*[KMG]?i?B/s)", line, re.I):
        speed = m.group(1)
    return prog, speed


def _parse_title(line: str) -> str | None:
    for pattern in (r"视频标题[：:]\s*(.+)", r"标题[：:]\s*(.+)", r"Title[：:]\s*(.+)"):
        if m := re.search(pattern, line):
            return m.group(1).strip()
    return None


def _parse_cover_url(line: str) -> str | None:
    if m := re.search(r"(https?://[^\s]+\.(?:jpg|jpeg|png|webp))", line, re.I):
        return m.group(1)
    return None


def _find_newest_output(work_dir: Path, before_ts: float) -> str:
    r"""
    在工作目录找到下载后最新创建/修改的媒体文件
    """
    best: Path | None = None
    best_mtime: float = before_ts
    media_exts: set[str] = {".mp4", ".mkv", ".flv", ".m4a", ".mp3", ".aac", ".xml", ".ass", ".srt"}
    try:
        for f in work_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() in media_exts:
                mt: float = f.stat().st_mtime
                if mt > best_mtime:
                    best_mtime = mt
                    best = f
    except Exception:
        pass
    return str(best) if best else ""


def _read_raw_lines(process: subprocess.Popen):
    r"""
    逐字节读取子进程输出, 按 \\r 和 \\n 分行, 使用系统编码解码
    """
    line_buf: bytearray = bytearray()
    while True:
        b: bytes = process.stdout.read(1)
        if not b:
            if process.poll() is not None:
                break
            continue
        if b == b"\n" or b == b"\r":
            if line_buf:
                try:
                    text: str = bytes(line_buf).decode(_CONSOLE_ENC, errors="replace")
                except Exception:
                    text = bytes(line_buf).decode("utf-8", errors="replace")
                line_buf.clear()
                yield text
            continue
        line_buf.extend(b)
    # 残留内容
    if line_buf:
        try:
            yield bytes(line_buf).decode(_CONSOLE_ENC, errors="replace")
        except Exception:
            yield bytes(line_buf).decode("utf-8", errors="replace")


def _worker_fn() -> None:
    while True:
        task: BBDownTask | None = None
        with S.lock:
            if S._cancel.is_set():
                S._worker = None
                S._cancel.clear()
                return
            for t in S.tasks:
                if t.status == "queued":
                    task = t
                    break
            if not task:
                S._worker = None
                return
            task.status = "downloading"
            task.progress = 0.0
            task.speed = ""

        S.log("info", f"开始下载: {task.url}")

        try:
            cmd: list[str] = _build_command(task)
            S.log("info", f"执行命令 ({len(cmd)} 个参数)")

            work_dir: Path = _get_work_dir()
            before_ts: float = datetime.now().timestamp()

            with S.lock:
                task.output_dir = str(work_dir)

            process: subprocess.Popen = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                **_POPEN_EXTRA,
            )

            with S.lock:
                S._process = process

            for raw_line in _read_raw_lines(process):
                clean_line: str = _clean(raw_line)
                if not clean_line:
                    continue

                if S._cancel.is_set():
                    process.kill()
                    break

                prog, spd = _parse_progress(clean_line)
                if prog is not None:
                    with S.lock:
                        task.progress = prog
                        if spd:
                            task.speed = spd
                    # 进度行不写入日志避免刷屏
                    continue

                S.log("info", clean_line)

                if title := _parse_title(clean_line):
                    with S.lock:
                        task.title = title

                if cover := _parse_cover_url(clean_line):
                    with S.lock:
                        task.cover_url = cover

            process.wait()

            with S.lock:
                S._process = None

            if S._cancel.is_set():
                with S.lock:
                    task.status = "cancelled"
                S.log("warn", f"已取消: {task.title or task.url}")
                S._cancel.clear()
                with S.lock:
                    S._worker = None
                return

            if process.returncode == 0:
                output_file: str = _find_newest_output(work_dir, before_ts)
                with S.lock:
                    task.status = "success"
                    task.progress = 1.0
                    task.output_file = output_file
                    S.tasks = [t for t in S.tasks if t.id != task.id]
                    S.completed.append(task)
                S.log("success", f"下载完成: {task.title or task.url}")
            else:
                with S.lock:
                    task.status = "failed"
                    task.error = f"退出码 {process.returncode}"
                S.log("error", f"下载失败: {task.title or task.url} (退出码 {process.returncode})")

        except Exception as e:
            with S.lock:
                task.status = "failed"
                task.error = str(e)
                S._process = None
            S.log("error", f"下载异常: {task.url} — {e}")

    with S.lock:
        S._worker = None


def _ensure_worker() -> None:
    with S.lock:
        if S._worker is None or not S._worker.is_alive():
            S._cancel.clear()
            t: threading.Thread = threading.Thread(target=_worker_fn, daemon=True)
            S._worker = t
            t.start()


def get_state() -> dict:
    return S.snapshot()


def env_check() -> dict[str, bool | str]:
    bbdown_path: str | None = _find_bbdown()
    ffmpeg_path: str | None = _find_ffmpeg()
    return {
        "bbdown_available": bbdown_path is not None,
        "bbdown_path": bbdown_path or "",
        "ffmpeg_available": ffmpeg_path is not None,
        "ffmpeg_path": ffmpeg_path or "",
        "has_sessdata": bool(utils.get_sessdata().strip()),
    }


def add_task(url: str, options: dict | None = None) -> dict:
    url = url.strip()
    if not url:
        return {"ok": False, "error": "URL 不能为空"}
    if not _find_bbdown():
        return {"ok": False, "error": "BBDown 未找到"}

    task: BBDownTask = BBDownTask(url=url, options=options or {})
    with S.lock:
        S.tasks.append(task)
    S.log("info", f"已添加任务: {url}")
    _ensure_worker()
    return {"ok": True, "task_id": task.id}


def cancel_current() -> None:
    S._cancel.set()
    with S.lock:
        if S._process:
            try:
                S._process.kill()
            except Exception:
                ...
    S.log("info", "正在取消当前下载...")


def remove_task(task_id: str) -> None:
    with S.lock:
        S.tasks = [t for t in S.tasks if not (t.id == task_id and t.status in ("queued", "failed", "cancelled"))]


def retry_task(task_id: str) -> dict:
    with S.lock:
        for t in S.tasks:
            if t.id == task_id and t.status in ("failed", "cancelled"):
                t.status = "queued"
                t.progress = 0.0
                t.speed = ""
                t.error = ""
                _ensure_worker()
                return {"ok": True}
    return {"ok": False, "error": "未找到可重试的任务"}


def clear_completed() -> None:
    with S.lock:
        S.completed.clear()
    S.log("info", "已清空完成列表")


def clear_failed() -> None:
    with S.lock:
        S.tasks = [t for t in S.tasks if t.status not in ("failed", "cancelled")]
    S.log("info", "已清空失败任务")


def clear_queue() -> None:
    with S.lock:
        S.tasks = [t for t in S.tasks if t.status != "queued"]
    S.log("info", "已清空排队任务")


def open_in_explorer(file_path: str) -> dict[str, bool | str]:
    r"""
    在资源管理器中定位文件或打开目录
    """
    if not file_path:
        return {"ok": False, "error": "路径为空"}
    p: Path = Path(file_path)
    try:
        if p.is_file():
            subprocess.Popen(["explorer", "/select,", str(p)], **_POPEN_EXTRA)
        elif p.is_dir():
            subprocess.Popen(["explorer", str(p)], **_POPEN_EXTRA)
        else:
            parent = p.parent
            if parent.is_dir():
                subprocess.Popen(["explorer", str(parent)], **_POPEN_EXTRA)
            else:
                return {"ok": False, "error": "路径不存在"}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    