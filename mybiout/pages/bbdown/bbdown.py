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

_控制码正则: 正则.Pattern[str] = 正则.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_子进程附加参数: dict[str, int] = {}
if 系统.platform == "win32":
    _子进程附加参数["creationflags"] = 0x08000000

_控制台编码: str = "gbk" if 系统.platform == "win32" else "utf-8"


def _取程序工具目录() -> 路径:
    r"""
    获取 bin 工具目录 (支持绿色旁路与冻结资源)
    :return: Path: bin 目录
    """
    return 工具.取工具目录()


def _寻找BBDown() -> str | None:
    r"""
    查找 BBDown 可执行文件
    :return: str | None: 可执行文件路径, 未找到返回 None
    """
    程序工具目录: 路径 = _取程序工具目录()
    候选路径列表: list[路径] = [
        程序工具目录 / "BBDown" / "BBDown.exe",
        程序工具目录 / "BBDown" / "BBDown",
        程序工具目录 / "BBDown.exe",
        程序工具目录 / "BBDown",
    ]
    for 候选路径 in 候选路径列表:
        if 候选路径.exists():
            工具.确保文件可执行(候选路径)
            return str(候选路径)
    系统路径 = 文件工具.which("BBDown") or 文件工具.which("bbdown")
    if 系统路径:
        工具.确保文件可执行(路径(系统路径))
    return 系统路径


def _寻找FFmpeg() -> str | None:
    r"""
    查找 ffmpeg 可执行文件
    :return: str | None: 可执行文件路径, 未找到返回 None
    """
    程序工具目录: 路径 = _取程序工具目录()
    候选路径列表: list[路径] = [
        程序工具目录 / "BBDown" / "ffmpeg.exe",
        程序工具目录 / "BBDown" / "ffmpeg",
        程序工具目录 / "ffmpeg.exe",
        程序工具目录 / "ffmpeg",
        程序工具目录 / "ffmpeg" / "ffmpeg.exe",
        程序工具目录 / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]
    for 候选路径 in 候选路径列表:
        if 候选路径.exists():
            工具.确保文件可执行(候选路径)
            return str(候选路径)
    系统路径 = 文件工具.which("ffmpeg")
    if 系统路径:
        工具.确保文件可执行(路径(系统路径))
    return 系统路径


def _生成编号() -> str:
    return 唯一编号.uuid4().hex[:12]


def _短时间() -> str:
    return 日期时间.now().strftime("%H:%M:%S")


def _完整时间() -> str:
    return 日期时间.now().strftime("%Y-%m-%d %H:%M:%S")


def _清理文本(行: str) -> str:
    return _控制码正则.sub("", 行).strip()


@数据类(slots=True)
class 下载任务:
    r"""
    BBDown 下载任务数据模型
    """

    编号: str = 字段(default_factory=_生成编号)
    链接: str = ""
    标题: str = ""
    状态名: str = "queued"
    进度: float = 0.0
    速度: str = ""
    错误: str = ""
    选项: dict = 字段(default_factory=dict)
    输出文件: str = ""
    输出目录: str = ""
    封面地址: str = ""
    创建时间: str = 字段(default_factory=_完整时间)

    def 转字典(自身) -> dict:
        return {
            "id": 自身.编号,
            "url": 自身.链接,
            "title": 自身.标题 or 自身.链接,
            "status": 自身.状态名,
            "progress": round(自身.进度, 3),
            "speed": 自身.速度,
            "error": 自身.错误,
            "options": 自身.选项,
            "output_file": 自身.输出文件,
            "output_dir": 自身.输出目录,
            "cover_url": 自身.封面地址,
            "created_at": 自身.创建时间,
        }


class _下载状态:
    def __init__(自身) -> None:
        自身.锁: 线程.RLock = 线程.RLock()
        自身.任务列表: list[下载任务] = []
        自身.完成列表: list[下载任务] = []
        自身.日志列表: list[dict] = []
        自身._工作线程: 线程.Thread | None = None
        自身._取消标记: 线程.Event = 线程.Event()
        自身._进程: 子进程.Popen | None = None

    def 记录日志(自身, 等级: str, 消息: str) -> None:
        with 自身.锁:
            自身.日志列表.append({"time": _短时间(), "level": 等级, "msg": 消息})
            if len(自身.日志列表) > 500:
                自身.日志列表 = 自身.日志列表[-300:]

    def 快照(自身) -> dict:
        with 自身.锁:
            return {
                "tasks": [任务项.转字典() for 任务项 in 自身.任务列表],
                "completed": [任务项.转字典() for 任务项 in 自身.完成列表],
                "logs": list(自身.日志列表),
                "is_downloading": any(任务项.状态名 == "downloading" for 任务项 in 自身.任务列表),
            }


状态: _下载状态 = _下载状态()


def _取工作目录() -> 路径:
    工作目录: 路径 = 工具.取导出路径() / 工具.取设置("bbdown", "folder")
    工作目录.mkdir(parents=True, exist_ok=True)
    return 工作目录


def _构建命令(任务: 下载任务) -> list[str]:
    下载器: str | None = _寻找BBDown()
    if not 下载器:
        raise RuntimeError("BBDown 可执行文件未找到")

    命令: list[str] = [下载器]
    选项表: dict = 任务.选项 or {}

    def _取布尔选项(键: str, 设置键: str | None = None) -> bool:
        r"""任务显式传值优先；未传时才继承 OhMyConfig 默认值。"""
        if 键 in 选项表:
            值 = 选项表[键]
            if isinstance(值, str):
                return 值.strip().lower() in {"1", "true", "yes", "on"}
            return bool(值)
        return 工具.取设置("bbdown", 设置键 or 键) == "true"

    会话数据: str = 工具.取会话数据().strip()
    if 会话数据:
        命令.extend(["-c", f"SESSDATA={会话数据}"])

    match 选项表.get("api_mode", "default"):
        case "tv":
            命令.append("-tv")
        case "app":
            命令.append("-app")
        case "intl":
            命令.append("-intl")

    画质: str = (选项表.get("quality", "") or 工具.取设置("bbdown", "quality_priority")).strip()
    if 画质:
        命令.extend(["-q", 画质])

    编码: str = (选项表.get("encoding", "") or 工具.取设置("bbdown", "encoding_priority")).strip()
    if 编码:
        命令.extend(["-e", 编码])

    内容: str = 选项表.get("content", "default")
    match 内容:
        case "audio_only":
            命令.append("--audio-only")
        case "video_only":
            命令.append("--video-only")
        case "danmaku_only":
            命令.append("--danmaku-only")
        case "sub_only":
            命令.append("--sub-only")
        case "cover_only":
            命令.append("--cover-only")

    要弹幕: bool = _取布尔选项("download_danmaku")
    if 要弹幕 and 内容 == "default":
        命令.append("-dd")

    要跳过字幕: bool = _取布尔选项("skip_subtitle")
    if 要跳过字幕:
        命令.append("--skip-subtitle")

    要AI字幕: bool = _取布尔选项("download_ai_subtitle")
    if 要AI字幕 and not 要跳过字幕:
        # BBDown 的 --skip-ai 是默认开启的布尔选项；显式 false 才会下载 AI 字幕。
        命令.append("--skip-ai=false")

    要跳过封面: bool = _取布尔选项("skip_cover")
    if 要跳过封面:
        命令.append("--skip-cover")

    分P: str = 选项表.get("page", "").strip()
    if 分P:
        命令.extend(["-p", 分P])

    语言: str = (选项表.get("language", "") or 工具.取设置("bbdown", "language")).strip()
    if 语言:
        命令.extend(["--language", 语言])

    文件命名: str = 工具.取设置("bbdown", "file_pattern").strip()
    if 文件命名:
        命令.extend(["-F", 文件命名])

    多文件命名: str = 工具.取设置("bbdown", "multi_file_pattern").strip()
    if 多文件命名:
        命令.extend(["-M", 多文件命名])

    工作目录: 路径 = _取工作目录()
    命令.extend(["--work-dir", str(工作目录)])

    if 工具.取设置("bbdown", "use_aria2c") == "true":
        命令.append("--use-aria2c")

    if 转码器 := _寻找FFmpeg():
        命令.extend(["--ffmpeg-path", 转码器])

    命令.append(任务.链接)
    return 命令


def _解析进度(行: str) -> tuple[float | None, str | None]:
    进度值: float | None = None
    速度: str | None = None
    if 匹配 := 正则.search(r"(\d+\.?\d*)%", 行):
        进度值 = min(float(匹配.group(1)) / 100.0, 1.0)
    if 匹配 := 正则.search(r"(\d+\.?\d*\s*[KMG]?i?B/s)", 行, 正则.I):
        速度 = 匹配.group(1)
    return 进度值, 速度


def _估算阶段进度(行: str) -> float | None:
    r"""BBDown 不总输出百分比，按其稳定的阶段日志提供保守进度。"""
    if "任务完成" in 行 or "下载" in 行 and "完毕" in 行:
        return 0.98
    if "清理临时文件" in 行:
        return 0.95
    if "合并" in 行:
        return 0.88
    if "开始下载" in 行:
        return 0.25
    if "已选择的流" in 行 or "条音频流" in 行 or "条视频流" in 行:
        return 0.18
    if "开始解析" in 行:
        return 0.10
    if "获取aid" in 行 or "获取视频信息" in 行 or "检测账号登录" in 行:
        return 0.04
    return None


def _解析标题(行: str) -> str | None:
    for 模式 in (r"视频标题[：:]\s*(.+)", r"标题[：:]\s*(.+)", r"Title[：:]\s*(.+)"):
        if 匹配 := 正则.search(模式, 行):
            return 匹配.group(1).strip()
    return None


def _解析封面地址(行: str) -> str | None:
    if 匹配 := 正则.search(r"(https?://[^\s]+\.(?:jpg|jpeg|png|webp))", 行, 正则.I):
        return 匹配.group(1)
    return None


def _寻找最新输出(工作目录: 路径, 开始时间戳: float) -> str:
    r"""
    在工作目录找到下载后最新创建/修改的媒体文件
    """
    最佳路径: 路径 | None = None
    最佳时间: float = 开始时间戳
    媒体后缀: set[str] = {".mp4", ".mkv", ".flv", ".m4a", ".mp3", ".aac", ".xml", ".ass", ".srt"}
    try:
        for 候选文件 in 工作目录.rglob("*"):
            if 候选文件.is_file() and 候选文件.suffix.lower() in 媒体后缀:
                修改时间: float = 候选文件.stat().st_mtime
                if 修改时间 > 最佳时间:
                    最佳时间 = 修改时间
                    最佳路径 = 候选文件
    except Exception:
        pass
    return str(最佳路径) if 最佳路径 else ""


def _读取原始行(进程: 子进程.Popen):
    r"""
    逐字节读取子进程输出, 按 \\r 和 \\n 分行, 使用系统编码解码
    """
    行缓存: bytearray = bytearray()
    while True:
        字节块: bytes = 进程.stdout.read(1)
        if not 字节块:
            if 进程.poll() is not None:
                break
            continue
        if 字节块 == b"\n" or 字节块 == b"\r":
            if 行缓存:
                try:
                    文本: str = bytes(行缓存).decode("utf-8")
                except Exception:
                    文本 = bytes(行缓存).decode(_控制台编码, errors="replace")
                行缓存.clear()
                yield 文本
            continue
        行缓存.extend(字节块)
    # 残留内容
    if 行缓存:
        try:
            yield bytes(行缓存).decode("utf-8")
        except Exception:
            yield bytes(行缓存).decode(_控制台编码, errors="replace")


def _工作线程函数() -> None:
    while True:
        任务: 下载任务 | None = None
        with 状态.锁:
            if 状态._取消标记.is_set():
                状态._工作线程 = None
                状态._取消标记.clear()
                return
            for 任务项 in 状态.任务列表:
                if 任务项.状态名 == "queued":
                    任务 = 任务项
                    break
            if not 任务:
                状态._工作线程 = None
                return
            任务.状态名 = "downloading"
            任务.进度 = 0.0
            任务.速度 = ""

        状态.记录日志("info", f"开始下载: {任务.链接}")

        try:
            命令: list[str] = _构建命令(任务)
            状态.记录日志("info", f"执行命令 ({len(命令)} 个参数)")

            工作目录: 路径 = _取工作目录()
            开始时间戳: float = 日期时间.now().timestamp()

            with 状态.锁:
                任务.输出目录 = str(工作目录)

            进程: 子进程.Popen = 子进程.Popen(
                命令,
                stdout=子进程.PIPE,
                stderr=子进程.STDOUT,
                bufsize=0,
                **_子进程附加参数,
            )

            with 状态.锁:
                状态._进程 = 进程
                # 部分 BBDown 下载器不打印百分比，先让界面明确进入工作态。
                任务.进度 = 0.01

            for 原始行 in _读取原始行(进程):
                干净行: str = _清理文本(原始行)
                if not 干净行:
                    continue

                if 状态._取消标记.is_set():
                    进程.kill()
                    break

                进度值, 速度文本 = _解析进度(干净行)
                if 进度值 is not None:
                    with 状态.锁:
                        任务.进度 = 进度值
                        if 速度文本:
                            任务.速度 = 速度文本
                    # 进度行不写入日志避免刷屏
                    continue

                if 阶段进度 := _估算阶段进度(干净行):
                    with 状态.锁:
                        任务.进度 = max(任务.进度, 阶段进度)

                状态.记录日志("info", 干净行)

                if 标题 := _解析标题(干净行):
                    with 状态.锁:
                        任务.标题 = 标题

                if 封面 := _解析封面地址(干净行):
                    with 状态.锁:
                        任务.封面地址 = 封面

            进程.wait()

            with 状态.锁:
                状态._进程 = None

            if 状态._取消标记.is_set():
                with 状态.锁:
                    任务.状态名 = "cancelled"
                状态.记录日志("warn", f"已取消: {任务.标题 or 任务.链接}")
                状态._取消标记.clear()
                with 状态.锁:
                    状态._工作线程 = None
                return

            if 进程.returncode == 0:
                输出文件: str = _寻找最新输出(工作目录, 开始时间戳)
                with 状态.锁:
                    任务.状态名 = "success"
                    任务.进度 = 1.0
                    任务.输出文件 = 输出文件
                    状态.任务列表 = [任务项 for 任务项 in 状态.任务列表 if 任务项.编号 != 任务.编号]
                    状态.完成列表.append(任务)
                状态.记录日志("success", f"下载完成: {任务.标题 or 任务.链接}")
            else:
                with 状态.锁:
                    任务.状态名 = "failed"
                    任务.错误 = f"退出码 {进程.returncode}"
                状态.记录日志("error", f"下载失败: {任务.标题 or 任务.链接} (退出码 {进程.returncode})")

        except Exception as e:
            with 状态.锁:
                任务.状态名 = "failed"
                任务.错误 = str(e)
                状态._进程 = None
            状态.记录日志("error", f"下载异常: {任务.链接} — {e}")

    with 状态.锁:
        状态._工作线程 = None


def _确保工作线程() -> None:
    with 状态.锁:
        if 状态._工作线程 is None or not 状态._工作线程.is_alive():
            状态._取消标记.clear()
            任务项: 线程.Thread = 线程.Thread(target=_工作线程函数, daemon=True)
            状态._工作线程 = 任务项
            任务项.start()


def 取状态() -> dict:
    return 状态.快照()


def 环境检查() -> dict[str, bool | str]:
    BBDown路径: str | None = _寻找BBDown()
    FFmpeg路径: str | None = _寻找FFmpeg()
    return {
        "bbdown_available": BBDown路径 is not None,
        "bbdown_path": BBDown路径 or "",
        "ffmpeg_available": FFmpeg路径 is not None,
        "ffmpeg_path": FFmpeg路径 or "",
        "has_sessdata": bool(工具.取会话数据().strip()),
    }


def _添加单任务(链接: str, 选项: dict | None = None) -> dict:
    任务: 下载任务 = 下载任务(链接=链接, 选项=选项 or {})
    with 状态.锁:
        状态.任务列表.append(任务)
    状态.记录日志("info", f"已添加任务: {链接}")
    _确保工作线程()
    return {"ok": True, "task_id": 任务.编号, "added": 1}


def 添加任务(链接: str, 选项: dict | None = None) -> dict:
    from mybiout.pages.batch_input import 解析批量输入

    原文: str = (链接 or "").strip()
    项们: list[str] = 解析批量输入(原文)
    if not 项们 and 原文:
        项们 = [原文]
    if not 项们:
        return {"ok": False, "error": "URL 不能为空"}
    if not _寻找BBDown():
        return {"ok": False, "error": "BBDown 未找到"}
    if len(项们) == 1:
        return _添加单任务(项们[0], 选项)
    编号们: list[str] = []
    for 项 in 项们:
        结果: dict = _添加单任务(项, 选项)
        if 结果.get("ok"):
            编号们.append(str(结果.get("task_id") or ""))
    return {"ok": True, "added": len(编号们), "task_ids": 编号们, "task_id": 编号们[0] if 编号们 else ""}


def 取消当前() -> None:
    状态._取消标记.set()
    with 状态.锁:
        if 状态._进程:
            with 忽略异常(Exception):
                状态._进程.kill()
    状态.记录日志("info", "正在取消当前下载...")


def 移除任务(任务编号: str) -> None:
    with 状态.锁:
        状态.任务列表 = [任务项 for 任务项 in 状态.任务列表 if not (任务项.编号 == 任务编号 and 任务项.状态名 in ("queued", "failed", "cancelled"))]


def 重试任务(任务编号: str) -> dict:
    with 状态.锁:
        for 任务项 in 状态.任务列表:
            if 任务项.编号 == 任务编号 and 任务项.状态名 in ("failed", "cancelled"):
                任务项.状态名 = "queued"
                任务项.进度 = 0.0
                任务项.速度 = ""
                任务项.错误 = ""
                _确保工作线程()
                return {"ok": True}
    return {"ok": False, "error": "未找到可重试的任务"}


def 清空完成() -> None:
    with 状态.锁:
        状态.完成列表.clear()
    状态.记录日志("info", "已清空完成列表")


def 清空失败() -> None:
    with 状态.锁:
        状态.任务列表 = [任务项 for 任务项 in 状态.任务列表 if 任务项.状态名 not in ("failed", "cancelled")]
    状态.记录日志("info", "已清空失败任务")


def 清空队列() -> None:
    with 状态.锁:
        状态.任务列表 = [任务项 for 任务项 in 状态.任务列表 if 任务项.状态名 != "queued"]
    状态.记录日志("info", "已清空排队任务")


def 在资源管理器中打开(文件路径: str) -> dict[str, bool | str]:
    r"""
    在系统文件管理器中定位文件或打开目录
    """
    return 工具.打开本地路径(文件路径)
