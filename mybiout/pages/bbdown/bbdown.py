"""BBDown! — BBDown 可视化封装 服务层"""

import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from mybiout.pages import utils

# ============================== 路径 ==============================

_BIN_DIR = Path(__file__).resolve().parent.parent.parent / "bin"
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_POPEN_EXTRA: dict = {}
if sys.platform == "win32":
    _POPEN_EXTRA["creationflags"] = 0x08000000  # CREATE_NO_WINDOW


def _find_bbdown() -> str | None:
    """查找 BBDown 可执行文件"""
    candidates = [
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
    """查找 ffmpeg"""
    candidates = [
        _BIN_DIR / "BBDown" / "ffmpeg.exe",
        _BIN_DIR / "BBDown" / "ffmpeg",
        _BIN_DIR / "ffmpeg.exe",
        _BIN_DIR / "ffmpeg",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return shutil.which("ffmpeg")


# ============================== 工具 ==============================


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _ts_full() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(line: str) -> str:
    return _ANSI_RE.sub("", line).strip()


# ============================== BBDownTask ==============================


class BBDownTask:
    __slots__ = (
        "id", "url", "title", "status", "progress", "speed",
        "error", "options", "output_file", "created_at",
    )

    def __init__(self, **kw):
        self.id: str = kw.get("id", _uid())
        self.url: str = kw.get("url", "")
        self.title: str = kw.get("title", "")
        self.status: str = kw.get("status", "queued")
        self.progress: float = kw.get("progress", 0.0)
        self.speed: str = kw.get("speed", "")
        self.error: str = kw.get("error", "")
        self.options: dict = kw.get("options", {})
        self.output_file: str = kw.get("output_file", "")
        self.created_at: str = kw.get("created_at", _ts_full())

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
            "created_at": self.created_at,
        }


# ============================== 全局状态 ==============================


class _State:
    def __init__(self):
        self.lock = threading.RLock()
        self.tasks: list[BBDownTask] = []
        self.completed: list[BBDownTask] = []
        self.logs: list[dict] = []
        self._worker: threading.Thread | None = None
        self._cancel = threading.Event()
        self._process: subprocess.Popen | None = None

    def log(self, level: str, msg: str):
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


S = _State()


# ============================== 命令构建 ==============================


def _build_command(task: BBDownTask) -> list[str]:
    """构建 BBDown 命令行"""
    bbdown = _find_bbdown()
    if not bbdown:
        raise RuntimeError("BBDown 可执行文件未找到")

    cmd = [bbdown]
    opts = task.options or {}

    # Cookie
    cookie = utils.get_setting("bbdown", "cookie").strip()
    if cookie:
        cmd.extend(["-c", f"SESSDATA={cookie}"])

    # API mode
    api_mode = opts.get("api_mode", "default")
    if api_mode == "tv":
        cmd.append("-tv")
    elif api_mode == "app":
        cmd.append("-app")
    elif api_mode == "intl":
        cmd.append("-intl")

    # Quality
    quality = opts.get("quality", "").strip()
    if not quality:
        quality = utils.get_setting("bbdown", "quality_priority").strip()
    if quality:
        cmd.extend(["-q", quality])

    # Encoding
    encoding = opts.get("encoding", "").strip()
    if not encoding:
        encoding = utils.get_setting("bbdown", "encoding_priority").strip()
    if encoding:
        cmd.extend(["-e", encoding])

    # Content type
    content = opts.get("content", "default")
    if content == "audio_only":
        cmd.append("--audio-only")
    elif content == "video_only":
        cmd.append("--video-only")
    elif content == "danmaku_only":
        cmd.append("--danmaku-only")
    elif content == "sub_only":
        cmd.append("--sub-only")
    elif content == "cover_only":
        cmd.append("--cover-only")

    # Download danmaku
    want_danmaku = opts.get("download_danmaku", False)
    if not want_danmaku:
        want_danmaku = utils.get_setting("bbdown", "download_danmaku") == "true"
    if want_danmaku and content == "default":
        cmd.append("-dd")

    # Skip options
    want_skip_sub = opts.get("skip_subtitle", False)
    if not want_skip_sub:
        want_skip_sub = utils.get_setting("bbdown", "skip_subtitle") == "true"
    if want_skip_sub:
        cmd.append("--skip-subtitle")

    want_skip_cover = opts.get("skip_cover", False)
    if not want_skip_cover:
        want_skip_cover = utils.get_setting("bbdown", "skip_cover") == "true"
    if want_skip_cover:
        cmd.append("--skip-cover")

    # Page selection
    page = opts.get("page", "").strip()
    if page:
        cmd.extend(["-p", page])

    # File pattern
    file_pattern = utils.get_setting("bbdown", "file_pattern").strip()
    if file_pattern:
        cmd.extend(["-F", file_pattern])
    multi_file_pattern = utils.get_setting("bbdown", "multi_file_pattern").strip()
    if multi_file_pattern:
        cmd.extend(["-M", multi_file_pattern])

    # Work directory
    export_root = utils.get_export_path()
    folder = utils.get_setting("bbdown", "folder")
    work_dir = export_root / folder
    work_dir.mkdir(parents=True, exist_ok=True)
    cmd.extend(["--work-dir", str(work_dir)])

    # aria2c
    if utils.get_setting("bbdown", "use_aria2c") == "true":
        cmd.append("--use-aria2c")

    # ffmpeg path (tell BBDown where ffmpeg is)
    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        cmd.extend(["--ffmpeg-path", ffmpeg])

    cmd.append(task.url)
    return cmd


# ============================== 解析 ==============================


def _parse_progress(line: str) -> tuple[float | None, str | None]:
    """尝试从 BBDown 输出解析进度和速度"""
    prog = None
    speed = None
    m = re.search(r"(\d+\.?\d*)%", line)
    if m:
        prog = min(float(m.group(1)) / 100.0, 1.0)
    m = re.search(r"(\d+\.?\d*\s*[KMG]?i?B/s)", line, re.I)
    if m:
        speed = m.group(1)
    return prog, speed


def _parse_title(line: str) -> str | None:
    """尝试从 BBDown 输出提取视频标题"""
    for pattern in [
        r"标题[：:]\s*(.+)",
        r"Title[：:]\s*(.+)",
        r"视频标题[：:]\s*(.+)",
    ]:
        m = re.search(pattern, line)
        if m:
            return m.group(1).strip()
    return None


# ============================== Worker ==============================


def _worker_fn():
    """后台 worker: 逐个处理下载队列"""
    while True:
        task = None
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
            cmd = _build_command(task)
            S.log("info", f"执行命令 ({len(cmd)} 个参数)")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **_POPEN_EXTRA,
            )

            with S.lock:
                S._process = process

            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if not line:
                    continue

                clean_line = _clean(line)
                if not clean_line:
                    continue

                S.log("info", clean_line)

                title = _parse_title(clean_line)
                if title:
                    with S.lock:
                        task.title = title

                prog, spd = _parse_progress(clean_line)
                with S.lock:
                    if prog is not None:
                        task.progress = prog
                    if spd:
                        task.speed = spd

                if S._cancel.is_set():
                    process.kill()
                    break

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
                with S.lock:
                    task.status = "success"
                    task.progress = 1.0
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


def _ensure_worker():
    with S.lock:
        if S._worker is None or not S._worker.is_alive():
            S._cancel.clear()
            t = threading.Thread(target=_worker_fn, daemon=True)
            S._worker = t
            t.start()


# ============================== 公共 API ==============================


def get_state() -> dict:
    return S.snapshot()


def env_check() -> dict:
    """环境检查"""
    bbdown_path = _find_bbdown()
    ffmpeg_path = _find_ffmpeg()
    return {
        "bbdown_available": bbdown_path is not None,
        "bbdown_path": bbdown_path or "",
        "ffmpeg_available": ffmpeg_path is not None,
        "ffmpeg_path": ffmpeg_path or "",
    }


def add_task(url: str, options: dict | None = None) -> dict:
    """添加下载任务"""
    url = url.strip()
    if not url:
        return {"ok": False, "error": "URL 不能为空"}
    if not _find_bbdown():
        return {"ok": False, "error": "BBDown 未找到"}

    task = BBDownTask(url=url, options=options or {})
    with S.lock:
        S.tasks.append(task)
    S.log("info", f"已添加任务: {url}")
    _ensure_worker()
    return {"ok": True, "task_id": task.id}


def cancel_current():
    """取消当前下载"""
    S._cancel.set()
    with S.lock:
        if S._process:
            try:
                S._process.kill()
            except Exception:
                pass
    S.log("info", "正在取消当前下载...")


def remove_task(task_id: str):
    """移除排队中的任务"""
    with S.lock:
        S.tasks = [t for t in S.tasks if not (t.id == task_id and t.status in ("queued", "failed", "cancelled"))]


def retry_task(task_id: str) -> dict:
    """重试失败/取消的任务"""
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


def clear_completed():
    """清空已完成列表"""
    with S.lock:
        S.completed.clear()
    S.log("info", "已清空完成列表")


def clear_failed():
    """清空失败/取消的任务"""
    with S.lock:
        S.tasks = [t for t in S.tasks if t.status not in ("failed", "cancelled")]
    S.log("info", "已清空失败任务")


def clear_queue():
    """清空排队中的任务"""
    with S.lock:
        S.tasks = [t for t in S.tasks if t.status != "queued"]
    S.log("info", "已清空排队任务")
    