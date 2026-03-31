r"""
BBDown! 可视化封装服务层, 管理 BBDown 下载任务队列

:file: mybiout/pages/bbdown/bbdown.py
:author: WaterRun
:time: 2026-03-31
"""

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


def _clean(line: str) -> str:
    r"""
    清除 ANSI 转义序列并去除首尾空白
    :param: line: 原始行文本
    :return: str: 清理后的文本
    """
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
    created_at: str = field(default_factory=_ts_full)

    def to_dict(self) -> dict:
        r"""
        转换为前端可用的字典
        :return: dict: 任务字典
        """
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


class _State:
    r"""
    BBDown 全局运行状态管理
    """

    def __init__(self) -> None:
        r"""
        初始化全局状态
        """
        self.lock: threading.RLock = threading.RLock()
        self.tasks: list[BBDownTask] = []
        self.completed: list[BBDownTask] = []
        self.logs: list[dict] = []
        self._worker: threading.Thread | None = None
        self._cancel: threading.Event = threading.Event()
        self._process: subprocess.Popen | None = None

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
                "tasks": [t.to_dict() for t in self.tasks],
                "completed": [t.to_dict() for t in self.completed],
                "logs": list(self.logs),
                "is_downloading": any(t.status == "downloading" for t in self.tasks),
            }


S: _State = _State()


def _build_command(task: BBDownTask) -> list[str]:
    r"""
    根据任务选项构建 BBDown 命令行参数列表
    :param: task: 下载任务
    :return: list[str]: 命令行参数列表
    :raise: RuntimeError: BBDown 未找到时抛出
    """
    bbdown: str | None = _find_bbdown()
    if not bbdown:
        raise RuntimeError("BBDown 可执行文件未找到")

    cmd: list[str] = [bbdown]
    opts: dict = task.options or {}

    cookie: str = utils.get_setting("bbdown", "cookie").strip()
    if cookie:
        cmd.extend(["-c", f"SESSDATA={cookie}"])

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

    work_dir: Path = utils.get_export_path() / utils.get_setting("bbdown", "folder")
    work_dir.mkdir(parents=True, exist_ok=True)
    cmd.extend(["--work-dir", str(work_dir)])

    if utils.get_setting("bbdown", "use_aria2c") == "true":
        cmd.append("--use-aria2c")

    if ffmpeg := _find_ffmpeg():
        cmd.extend(["--ffmpeg-path", ffmpeg])

    cmd.append(task.url)
    return cmd


def _parse_progress(line: str) -> tuple[float | None, str | None]:
    r"""
    从 BBDown 输出行解析下载进度和速度
    :param: line: 输出行文本
    :return: tuple[float | None, str | None]: (进度, 速度)
    """
    prog: float | None = None
    speed: str | None = None
    if m := re.search(r"(\d+\.?\d*)%", line):
        prog = min(float(m.group(1)) / 100.0, 1.0)
    if m := re.search(r"(\d+\.?\d*\s*[KMG]?i?B/s)", line, re.I):
        speed = m.group(1)
    return prog, speed


def _parse_title(line: str) -> str | None:
    r"""
    从 BBDown 输出行提取视频标题
    :param: line: 输出行文本
    :return: str | None: 标题或 None
    """
    for pattern in (r"标题[：:]\s*(.+)", r"Title[：:]\s*(.+)", r"视频标题[：:]\s*(.+)"):
        if m := re.search(pattern, line):
            return m.group(1).strip()
    return None


def _worker_fn() -> None:
    r"""
    后台 worker 线程函数, 逐个处理下载队列
    """
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

            process: subprocess.Popen = subprocess.Popen(
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
                line: str = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if not (clean_line := _clean(line)):
                    continue

                S.log("info", clean_line)

                if title := _parse_title(clean_line):
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


def _ensure_worker() -> None:
    r"""
    确保后台 worker 线程正在运行
    """
    with S.lock:
        if S._worker is None or not S._worker.is_alive():
            S._cancel.clear()
            t: threading.Thread = threading.Thread(target=_worker_fn, daemon=True)
            S._worker = t
            t.start()


def get_state() -> dict:
    r"""
    获取当前状态快照
    :return: dict: 状态数据
    """
    return S.snapshot()


def env_check() -> dict[str, bool | str]:
    r"""
    检查运行环境中 BBDown 和 ffmpeg 的可用性
    :return: dict[str, bool | str]: 环境检测结果
    """
    bbdown_path: str | None = _find_bbdown()
    ffmpeg_path: str | None = _find_ffmpeg()
    return {
        "bbdown_available": bbdown_path is not None,
        "bbdown_path": bbdown_path or "",
        "ffmpeg_available": ffmpeg_path is not None,
        "ffmpeg_path": ffmpeg_path or "",
    }


def add_task(url: str, options: dict | None = None) -> dict:
    r"""
    添加下载任务到队列
    :param: url: 视频链接或 ID
    :param: options: 下载选项字典
    :return: dict: 添加结果
    """
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
    r"""
    取消当前正在进行的下载
    """
    S._cancel.set()
    with S.lock:
        if S._process:
            try:
                S._process.kill()
            except Exception:
                ...
    S.log("info", "正在取消当前下载...")


def remove_task(task_id: str) -> None:
    r"""
    移除排队中或失败的任务
    :param: task_id: 任务 ID
    """
    with S.lock:
        S.tasks = [t for t in S.tasks if not (t.id == task_id and t.status in ("queued", "failed", "cancelled"))]


def retry_task(task_id: str) -> dict:
    r"""
    重试失败或取消的任务
    :param: task_id: 任务 ID
    :return: dict: 操作结果
    """
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
    r"""
    清空已完成列表
    """
    with S.lock:
        S.completed.clear()
    S.log("info", "已清空完成列表")


def clear_failed() -> None:
    r"""
    清空失败和取消的任务
    """
    with S.lock:
        S.tasks = [t for t in S.tasks if t.status not in ("failed", "cancelled")]
    S.log("info", "已清空失败任务")


def clear_queue() -> None:
    r"""
    清空排队中的任务
    """
    with S.lock:
        S.tasks = [t for t in S.tasks if t.status != "queued"]
    S.log("info", "已清空排队任务")
    