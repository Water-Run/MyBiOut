r"""
BBDown! 可视化封装服务层, 管理 BBDown 下载任务队列

:file: mybiout/pages/bbdown/bbdown.py
:author: WaterRun
:time: 2026-04-06
"""

import re as 正则
import shutil as 文件工具
import subprocess as 子进程
import sys as 系统
import threading as 线程
import uuid as 唯一编号
from contextlib import suppress as 忽略异常
from dataclasses import dataclass as 数据类
from dataclasses import field as 字段
from datetime import datetime as 日期时间
from pathlib import Path as 路径

from mybiout.pages import utils as 工具

_BIN_DIR: 路径 = 路径(__file__).resolve().parent.parent.parent / "bin"
_ANSI_RE: 正则.Pattern[str] = 正则.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_POPEN_EXTRA: dict[str, int] = {}
if 系统.platform == "win32":
    _POPEN_EXTRA["creationflags"] = 0x08000000

_CONSOLE_ENC: str = "gbk" if 系统.platform == "win32" else "utf-8"


def _寻找BBDown() -> str | None:
    r"""
    查找 BBDown 可执行文件
    :return: str | None: 可执行文件路径, 未找到返回 None
    """
    candidates: list[路径] = [
        _BIN_DIR / "BBDown" / "BBDown.exe",
        _BIN_DIR / "BBDown" / "BBDown",
        _BIN_DIR / "BBDown.exe",
        _BIN_DIR / "BBDown",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return 文件工具.which("BBDown") or 文件工具.which("bbdown")


def _寻找FFmpeg() -> str | None:
    r"""
    查找 ffmpeg 可执行文件
    :return: str | None: 可执行文件路径, 未找到返回 None
    """
    candidates: list[路径] = [
        _BIN_DIR / "BBDown" / "ffmpeg.exe",
        _BIN_DIR / "BBDown" / "ffmpeg",
        _BIN_DIR / "ffmpeg.exe",
        _BIN_DIR / "ffmpeg",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return 文件工具.which("ffmpeg")


def _生成编号() -> str:
    return 唯一编号.uuid4().hex[:12]


def _短时间() -> str:
    return 日期时间.now().strftime("%H:%M:%S")


def _完整时间() -> str:
    return 日期时间.now().strftime("%Y-%m-%d %H:%M:%S")


def _清理文本(line: str) -> str:
    return _ANSI_RE.sub("", line).strip()


@数据类(slots=True)
class 下载任务:
    r"""
    BBDown 下载任务数据模型
    """

    id: str = 字段(default_factory=_生成编号)
    url: str = ""
    title: str = ""
    status: str = "queued"
    progress: float = 0.0
    speed: str = ""
    error: str = ""
    options: dict = 字段(default_factory=dict)
    output_file: str = ""
    output_dir: str = ""
    cover_url: str = ""
    created_at: str = 字段(default_factory=_完整时间)

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


class _下载状态:
    def __init__(self) -> None:
        self.lock: 线程.RLock = 线程.RLock()
        self.tasks: list[下载任务] = []
        self.completed: list[下载任务] = []
        self.logs: list[dict] = []
        self._worker: 线程.Thread | None = None
        self._cancel: 线程.Event = 线程.Event()
        self._process: 子进程.Popen | None = None

    def log(self, level: str, msg: str) -> None:
        with self.lock:
            self.logs.append({"time": _短时间(), "level": level, "msg": msg})
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


状态: _下载状态 = _下载状态()


def _取工作目录() -> 路径:
    work_dir: 路径 = 工具.取导出路径() / 工具.取设置("bbdown", "folder")
    work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir


def _构建命令(task: 下载任务) -> list[str]:
    bbdown: str | None = _寻找BBDown()
    if not bbdown:
        raise RuntimeError("BBDown 可执行文件未找到")

    cmd: list[str] = [bbdown]
    opts: dict = task.options or {}

    sessdata: str = 工具.取会话数据().strip()
    if sessdata:
        cmd.extend(["-c", f"SESSDATA={sessdata}"])

    match opts.get("api_mode", "default"):
        case "tv":
            cmd.append("-tv")
        case "app":
            cmd.append("-app")
        case "intl":
            cmd.append("-intl")

    quality: str = (opts.get("quality", "") or 工具.取设置("bbdown", "quality_priority")).strip()
    if quality:
        cmd.extend(["-q", quality])

    encoding: str = (opts.get("encoding", "") or 工具.取设置("bbdown", "encoding_priority")).strip()
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

    want_danmaku: bool = (
        opts.get("download_danmaku", False) or 工具.取设置("bbdown", "download_danmaku") == "true"
    )
    if want_danmaku and content == "default":
        cmd.append("-dd")

    want_skip_sub: bool = opts.get("skip_subtitle", False) or 工具.取设置("bbdown", "skip_subtitle") == "true"
    if want_skip_sub:
        cmd.append("--skip-subtitle")

    want_skip_cover: bool = opts.get("skip_cover", False) or 工具.取设置("bbdown", "skip_cover") == "true"
    if want_skip_cover:
        cmd.append("--skip-cover")

    page: str = opts.get("page", "").strip()
    if page:
        cmd.extend(["-p", page])

    file_pattern: str = 工具.取设置("bbdown", "file_pattern").strip()
    if file_pattern:
        cmd.extend(["-F", file_pattern])

    multi_file_pattern: str = 工具.取设置("bbdown", "multi_file_pattern").strip()
    if multi_file_pattern:
        cmd.extend(["-M", multi_file_pattern])

    work_dir: 路径 = _取工作目录()
    cmd.extend(["--work-dir", str(work_dir)])

    if 工具.取设置("bbdown", "use_aria2c") == "true":
        cmd.append("--use-aria2c")

    if ffmpeg := _寻找FFmpeg():
        cmd.extend(["--ffmpeg-path", ffmpeg])

    cmd.append(task.url)
    return cmd


def _解析进度(line: str) -> tuple[float | None, str | None]:
    prog: float | None = None
    speed: str | None = None
    if m := 正则.search(r"(\d+\.?\d*)%", line):
        prog = min(float(m.group(1)) / 100.0, 1.0)
    if m := 正则.search(r"(\d+\.?\d*\s*[KMG]?i?B/s)", line, 正则.I):
        speed = m.group(1)
    return prog, speed


def _解析标题(line: str) -> str | None:
    for pattern in (r"视频标题[：:]\s*(.+)", r"标题[：:]\s*(.+)", r"Title[：:]\s*(.+)"):
        if m := 正则.search(pattern, line):
            return m.group(1).strip()
    return None


def _解析封面地址(line: str) -> str | None:
    if m := 正则.search(r"(https?://[^\s]+\.(?:jpg|jpeg|png|webp))", line, 正则.I):
        return m.group(1)
    return None


def _寻找最新输出(work_dir: 路径, before_ts: float) -> str:
    r"""
    在工作目录找到下载后最新创建/修改的媒体文件
    """
    best: 路径 | None = None
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


def _读取原始行(process: 子进程.Popen):
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


def _工作线程函数() -> None:
    while True:
        task: 下载任务 | None = None
        with 状态.lock:
            if 状态._cancel.is_set():
                状态._worker = None
                状态._cancel.clear()
                return
            for t in 状态.tasks:
                if t.status == "queued":
                    task = t
                    break
            if not task:
                状态._worker = None
                return
            task.status = "downloading"
            task.progress = 0.0
            task.speed = ""

        状态.log("info", f"开始下载: {task.url}")

        try:
            cmd: list[str] = _构建命令(task)
            状态.log("info", f"执行命令 ({len(cmd)} 个参数)")

            work_dir: 路径 = _取工作目录()
            before_ts: float = 日期时间.now().timestamp()

            with 状态.lock:
                task.output_dir = str(work_dir)

            process: 子进程.Popen = 子进程.Popen(
                cmd,
                stdout=子进程.PIPE,
                stderr=子进程.STDOUT,
                bufsize=0,
                **_POPEN_EXTRA,
            )

            with 状态.lock:
                状态._process = process

            for raw_line in _读取原始行(process):
                clean_line: str = _清理文本(raw_line)
                if not clean_line:
                    continue

                if 状态._cancel.is_set():
                    process.kill()
                    break

                prog, spd = _解析进度(clean_line)
                if prog is not None:
                    with 状态.lock:
                        task.progress = prog
                        if spd:
                            task.speed = spd
                    # 进度行不写入日志避免刷屏
                    continue

                状态.log("info", clean_line)

                if title := _解析标题(clean_line):
                    with 状态.lock:
                        task.title = title

                if cover := _解析封面地址(clean_line):
                    with 状态.lock:
                        task.cover_url = cover

            process.wait()

            with 状态.lock:
                状态._process = None

            if 状态._cancel.is_set():
                with 状态.lock:
                    task.status = "cancelled"
                状态.log("warn", f"已取消: {task.title or task.url}")
                状态._cancel.clear()
                with 状态.lock:
                    状态._worker = None
                return

            if process.returncode == 0:
                output_file: str = _寻找最新输出(work_dir, before_ts)
                with 状态.lock:
                    task.status = "success"
                    task.progress = 1.0
                    task.output_file = output_file
                    状态.tasks = [t for t in 状态.tasks if t.id != task.id]
                    状态.completed.append(task)
                状态.log("success", f"下载完成: {task.title or task.url}")
            else:
                with 状态.lock:
                    task.status = "failed"
                    task.error = f"退出码 {process.returncode}"
                状态.log("error", f"下载失败: {task.title or task.url} (退出码 {process.returncode})")

        except Exception as e:
            with 状态.lock:
                task.status = "failed"
                task.error = str(e)
                状态._process = None
            状态.log("error", f"下载异常: {task.url} — {e}")

    with 状态.lock:
        状态._worker = None


def _确保工作线程() -> None:
    with 状态.lock:
        if 状态._worker is None or not 状态._worker.is_alive():
            状态._cancel.clear()
            t: 线程.Thread = 线程.Thread(target=_工作线程函数, daemon=True)
            状态._worker = t
            t.start()


def 取状态() -> dict:
    return 状态.snapshot()


def 环境检查() -> dict[str, bool | str]:
    bbdown_path: str | None = _寻找BBDown()
    ffmpeg_path: str | None = _寻找FFmpeg()
    return {
        "bbdown_available": bbdown_path is not None,
        "bbdown_path": bbdown_path or "",
        "ffmpeg_available": ffmpeg_path is not None,
        "ffmpeg_path": ffmpeg_path or "",
        "has_sessdata": bool(工具.取会话数据().strip()),
    }


def 添加任务(url: str, options: dict | None = None) -> dict:
    url = url.strip()
    if not url:
        return {"ok": False, "error": "URL 不能为空"}
    if not _寻找BBDown():
        return {"ok": False, "error": "BBDown 未找到"}

    task: 下载任务 = 下载任务(url=url, options=options or {})
    with 状态.lock:
        状态.tasks.append(task)
    状态.log("info", f"已添加任务: {url}")
    _确保工作线程()
    return {"ok": True, "task_id": task.id}


def 取消当前() -> None:
    状态._cancel.set()
    with 状态.lock:
        if 状态._process:
            with 忽略异常(Exception):
                状态._process.kill()
    状态.log("info", "正在取消当前下载...")


def 移除任务(task_id: str) -> None:
    with 状态.lock:
        状态.tasks = [t for t in 状态.tasks if not (t.id == task_id and t.status in ("queued", "failed", "cancelled"))]


def 重试任务(task_id: str) -> dict:
    with 状态.lock:
        for t in 状态.tasks:
            if t.id == task_id and t.status in ("failed", "cancelled"):
                t.status = "queued"
                t.progress = 0.0
                t.speed = ""
                t.error = ""
                _确保工作线程()
                return {"ok": True}
    return {"ok": False, "error": "未找到可重试的任务"}


def 清空完成() -> None:
    with 状态.lock:
        状态.completed.clear()
    状态.log("info", "已清空完成列表")


def 清空失败() -> None:
    with 状态.lock:
        状态.tasks = [t for t in 状态.tasks if t.status not in ("failed", "cancelled")]
    状态.log("info", "已清空失败任务")


def 清空队列() -> None:
    with 状态.lock:
        状态.tasks = [t for t in 状态.tasks if t.status != "queued"]
    状态.log("info", "已清空排队任务")


def 在资源管理器中打开(file_path: str) -> dict[str, bool | str]:
    r"""
    在资源管理器中定位文件或打开目录
    """
    if not file_path:
        return {"ok": False, "error": "路径为空"}
    p: 路径 = 路径(file_path)
    try:
        if p.is_file():
            子进程.Popen(["explorer", "/select,", str(p)], **_POPEN_EXTRA)
        elif p.is_dir():
            子进程.Popen(["explorer", str(p)], **_POPEN_EXTRA)
        else:
            parent = p.parent
            if parent.is_dir():
                子进程.Popen(["explorer", str(parent)], **_POPEN_EXTRA)
            else:
                return {"ok": False, "error": "路径不存在"}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


_find_bbdown = _寻找BBDown
_find_ffmpeg = _寻找FFmpeg
_uid = _生成编号
_ts = _短时间
_ts_full = _完整时间
_clean = _清理文本
BBDownTask = 下载任务
_State = _下载状态
S = 状态
_get_work_dir = _取工作目录
_build_command = _构建命令
_parse_progress = _解析进度
_parse_title = _解析标题
_parse_cover_url = _解析封面地址
_find_newest_output = _寻找最新输出
_read_raw_lines = _读取原始行
_worker_fn = _工作线程函数
_ensure_worker = _确保工作线程
get_state = 取状态
env_check = 环境检查
add_task = 添加任务
cancel_current = 取消当前
remove_task = 移除任务
retry_task = 重试任务
clear_completed = 清空完成
clear_failed = 清空失败
clear_queue = 清空队列
open_in_explorer = 在资源管理器中打开
