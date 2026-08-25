r"""
LocalOut! 元文件归档恢复工具。

将“一个 MP4 + 三个缓存元文件”的 MyBiOut 归档重新构造成哔哩哔哩
Android 客户端可识别的缓存目录，并通过 ADB 校验后导入目标设备。
"""

from __future__ import annotations

import hashlib as 哈希
import json as 数据交换
import os as 系统
import re as 正则
import shlex as 命令行转义
import shutil as 文件工具
import subprocess as 子进程
import sys as 系统信息
import uuid as 唯一编号
from collections.abc import Callable as 可调用
from collections.abc import Iterable as 可迭代
from dataclasses import dataclass as 数据类
from datetime import datetime as 日期时间
from pathlib import Path as 路径


_子进程附加参数: dict = {}
if 系统信息.platform == "win32":
    _子进程附加参数["creationflags"] = 0x08000000

_安卓包名格式 = 正则.compile(r"^[A-Za-z0-9._]+$")
_允许的缓存布局: tuple[str, ...] = ("download", "files/download")
进度回调 = 可调用[[float, str], None]


class 缓存已存在错误(RuntimeError):
    r"""目标设备已存在同一 avid 时使用的可跳过异常。"""


@数据类(frozen=True, slots=True)
class 恢复归档:
    目录: 路径
    视频文件: 路径
    弹幕文件: 路径
    条目文件: 路径
    索引文件: 路径
    标题: str
    稿件号: str
    分集目录: str
    清晰度目录: str
    字节数: int

    @property
    def 相对缓存路径(自身) -> str:
        return f"{自身.稿件号}/{自身.分集目录}/{自身.清晰度目录}"

    @property
    def 标识(自身) -> str:
        原文 = 系统.path.normcase(str(自身.目录.resolve()))
        return 哈希.sha256(原文.encode("utf-8")).hexdigest()[:20]

    def 转字典(自身) -> dict:
        return {
            "id": 自身.标识,
            "path": str(自身.目录),
            "title": 自身.标题,
            "avid": 自身.稿件号,
            "cache_path": 自身.相对缓存路径,
            "mp4_name": 自身.视频文件.name,
            "size_bytes": 自身.字节数,
            "size_mb": round(自身.字节数 / 1048576, 1),
        }


def _报告(回调: 进度回调 | None, 进度: float, 消息: str) -> None:
    if 回调:
        回调(max(0.0, min(1.0, 进度)), 消息)


def _读取JSON(文件路径: 路径) -> dict:
    try:
        数据 = 数据交换.loads(文件路径.read_text(encoding="utf-8"))
    except (OSError, 数据交换.JSONDecodeError) as 异常:
        raise RuntimeError(f"无法读取 {文件路径.name}: {异常}") from 异常
    if not isinstance(数据, dict):
        raise RuntimeError(f"{文件路径.name} 的根节点不是对象")
    return 数据


def _缓存坐标(条目数据: dict) -> tuple[str, str, str]:
    稿件号: str = str(条目数据.get("avid") or "").strip()
    分集数据 = 条目数据.get("page_data")
    分集号: str = str(分集数据.get("cid") if isinstance(分集数据, dict) else "").strip()
    清晰度: str = str(条目数据.get("type_tag") or 条目数据.get("video_quality") or "").strip()
    for 名称, 值 in (("avid", 稿件号), ("cid", 分集号), ("type_tag", 清晰度)):
        if not 值.isdigit():
            raise RuntimeError(f"entry.json 中的 {名称} 无效: {值!r}")
    return 稿件号, f"c_{分集号}", 清晰度


def 检查恢复归档(归档路径: str | 路径) -> 恢复归档:
    目录 = 路径(归档路径).expanduser()
    if not 目录.is_dir():
        raise RuntimeError(f"存档文件夹不存在: {目录}")

    条目文件 = 目录 / "entry.json"
    索引文件 = 目录 / "index.json"
    弹幕文件 = 目录 / "danmaku.xml"
    for 文件路径 in (条目文件, 索引文件, 弹幕文件):
        if not 文件路径.is_file():
            raise RuntimeError(f"存档缺少 {文件路径.name}")

    视频列表 = [
        文件路径
        for 文件路径 in 目录.iterdir()
        if 文件路径.is_file() and 文件路径.suffix.lower() == ".mp4"
    ]
    if len(视频列表) != 1:
        raise RuntimeError(f"存档必须且只能包含一个 MP4，当前找到 {len(视频列表)} 个")

    条目数据 = _读取JSON(条目文件)
    索引数据 = _读取JSON(索引文件)
    视频索引 = 索引数据.get("video")
    音频索引 = 索引数据.get("audio")
    if not isinstance(视频索引, list) or not 视频索引 or not isinstance(视频索引[0], dict):
        raise RuntimeError("index.json 缺少 video[0]")
    if not isinstance(音频索引, list) or not 音频索引 or not isinstance(音频索引[0], dict):
        raise RuntimeError("index.json 缺少 audio[0]")

    稿件号, 分集目录, 清晰度目录 = _缓存坐标(条目数据)
    标题 = str(条目数据.get("title") or 视频列表[0].stem).strip()
    return 恢复归档(
        目录=目录,
        视频文件=视频列表[0],
        弹幕文件=弹幕文件,
        条目文件=条目文件,
        索引文件=索引文件,
        标题=标题,
        稿件号=稿件号,
        分集目录=分集目录,
        清晰度目录=清晰度目录,
        字节数=视频列表[0].stat().st_size,
    )


def 扫描恢复归档目录(根目录路径: str | 路径) -> tuple[list[恢复归档], list[str]]:
    r"""递归发现归档四件套；不依赖导出索引，也不跟随目录链接。"""
    根目录 = 路径(根目录路径).expanduser()
    if not 根目录.is_dir():
        raise RuntimeError(f"扫描文件夹不存在: {根目录}")

    归档列表: list[恢复归档] = []
    警告列表: list[str] = []
    必需文件名 = {"entry.json", "index.json", "danmaku.xml"}
    for 当前目录文本, 子目录名列表, 文件名列表 in 系统.walk(根目录, followlinks=False):
        当前目录 = 路径(当前目录文本)
        子目录名列表[:] = sorted(
            名称 for 名称 in 子目录名列表 if not (当前目录 / 名称).is_symlink()
        )
        文件名集合 = set(文件名列表)
        MP4数量 = sum(1 for 名称 in 文件名列表 if 名称.lower().endswith(".mp4"))
        if not (必需文件名 <= 文件名集合 and MP4数量 == 1):
            if MP4数量 and 必需文件名.intersection(文件名集合):
                缺少 = sorted(必需文件名 - 文件名集合)
                详情 = f"缺少 {', '.join(缺少)}" if 缺少 else f"找到 {MP4数量} 个 MP4"
                警告列表.append(f"跳过不完整归档 {当前目录}: {详情}")
            continue
        try:
            归档列表.append(检查恢复归档(当前目录))
            子目录名列表.clear()
        except Exception as 异常:
            警告列表.append(f"跳过无效归档 {当前目录}: {异常}")

    归档列表.sort(
        key=lambda 归档: (
            int(归档.稿件号),
            int(归档.分集目录.removeprefix("c_")),
            int(归档.清晰度目录),
            str(归档.目录).casefold(),
        )
    )
    return 归档列表, 警告列表


def _文件MD5(文件路径: 路径) -> str:
    摘要 = 哈希.md5()
    with 文件路径.open("rb") as 文件流:
        for 数据块 in iter(lambda: 文件流.read(8 * 1024 * 1024), b""):
            摘要.update(数据块)
    return 摘要.hexdigest()


def _写JSON并保留时间(目标路径: 路径, 数据: dict, 来源路径: 路径) -> None:
    来源状态 = 来源路径.stat()
    目标路径.write_text(
        数据交换.dumps(数据, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    系统.utime(目标路径, ns=(来源状态.st_atime_ns, 来源状态.st_mtime_ns))


def _执行命令(命令: list[str], *, 超时秒数: float = 1800, 检查: bool = True) -> 子进程.CompletedProcess:
    try:
        结果 = 子进程.run(
            命令,
            stdin=子进程.DEVNULL,
            stdout=子进程.PIPE,
            stderr=子进程.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=超时秒数,
            **_子进程附加参数,
        )
    except 子进程.TimeoutExpired as 异常:
        raise RuntimeError(f"命令执行超时: {命令[0]}") from 异常
    if 检查 and 结果.returncode != 0:
        错误文本 = (结果.stderr or 结果.stdout or "命令执行失败").strip()
        raise RuntimeError(f"{路径(命令[0]).name} 执行失败: {错误文本[-800:]}")
    return 结果


def _拆分媒体流(FFmpeg路径: str, MP4路径: 路径, 流选择: str, 输出路径: 路径) -> None:
    _执行命令(
        [
            FFmpeg路径,
            "-y",
            "-v",
            "error",
            "-i",
            str(MP4路径),
            "-map",
            流选择,
            "-c",
            "copy",
            "-movflags",
            "+dash",
            "-f",
            "mp4",
            str(输出路径),
        ]
    )
    if not 输出路径.is_file() or 输出路径.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg 未生成 {输出路径.name}")


def _更新索引(索引数据: dict, 视频路径: 路径, 音频路径: 路径) -> None:
    视频索引 = 索引数据["video"][0]
    音频索引 = 索引数据["audio"][0]
    视频索引["size"] = 视频路径.stat().st_size
    视频索引["md5"] = _文件MD5(视频路径)
    音频索引["size"] = 音频路径.stat().st_size
    音频索引["md5"] = _文件MD5(音频路径)


def _重建归档分集(
    归档: 恢复归档,
    稿件目录: 路径,
    FFmpeg路径: str,
    回调: 进度回调 | None = None,
) -> None:
    元数据目录 = 稿件目录 / 归档.分集目录
    媒体目录 = 元数据目录 / 归档.清晰度目录
    if 元数据目录.exists():
        raise RuntimeError(f"同一 avid 中存在重复分集目录: {归档.分集目录}")

    条目数据 = _读取JSON(归档.条目文件)
    索引数据 = _读取JSON(归档.索引文件)
    媒体目录.mkdir(parents=True)
    文件工具.copy2(归档.弹幕文件, 元数据目录 / "danmaku.xml")

    视频路径 = 媒体目录 / "video.m4s"
    音频路径 = 媒体目录 / "audio.m4s"
    _报告(回调, 0.12, f"拆分视频流: {归档.标题}")
    _拆分媒体流(FFmpeg路径, 归档.视频文件, "0:v:0", 视频路径)
    _报告(回调, 0.42, f"拆分音频流: {归档.标题}")
    _拆分媒体流(FFmpeg路径, 归档.视频文件, "0:a:0", 音频路径)

    _报告(回调, 0.78, f"更新校验信息: {归档.标题}")
    _更新索引(索引数据, 视频路径, 音频路径)
    总字节数 = 视频路径.stat().st_size + 音频路径.stat().st_size
    条目数据["has_dash_audio"] = True
    条目数据["is_completed"] = True
    条目数据["total_bytes"] = 总字节数
    条目数据["downloaded_bytes"] = 总字节数
    条目数据["guessed_total_bytes"] = 0
    _写JSON并保留时间(元数据目录 / "entry.json", 条目数据, 归档.条目文件)
    _写JSON并保留时间(媒体目录 / "index.json", 索引数据, 归档.索引文件)
    _报告(回调, 1.0, f"分集已重建: {归档.相对缓存路径}")


def 重建缓存组(
    归档集合: 可迭代[恢复归档],
    输出根目录: str | 路径,
    FFmpeg路径: str,
    回调: 进度回调 | None = None,
) -> 路径:
    r"""将同一 avid 的多个分集合并为一棵缓存树，并原子写入输出目录。"""
    if not FFmpeg路径 or not 路径(FFmpeg路径).is_file():
        raise RuntimeError("未找到 ffmpeg，无法拆分 MP4")

    归档列表 = list(归档集合)
    if not 归档列表:
        raise RuntimeError("没有可重建的缓存归档")
    稿件号 = 归档列表[0].稿件号
    if any(归档.稿件号 != 稿件号 for 归档 in 归档列表):
        raise RuntimeError("缓存组中包含不同 avid")
    分集目录列表 = [归档.分集目录 for 归档 in 归档列表]
    if len(set(分集目录列表)) != len(分集目录列表):
        raise RuntimeError(f"av{稿件号} 中包含重复 cid，无法确定应恢复哪个版本")

    输出根 = 路径(输出根目录)
    输出根.mkdir(parents=True, exist_ok=True)
    最终目录 = 输出根 / 稿件号
    if 最终目录.exists():
        raise RuntimeError(f"拒绝覆盖已存在的还原目录: {最终目录}")

    临时目录 = 输出根 / f".{稿件号}.restore-{唯一编号.uuid4().hex}"
    try:
        临时目录.mkdir()
        总数 = len(归档列表)
        for 序号, 归档 in enumerate(归档列表):
            def 分集进度(进度: float, 消息: str, *, _序号: int = 序号) -> None:
                _报告(回调, (_序号 + 进度) / 总数, 消息)

            _重建归档分集(归档, 临时目录, FFmpeg路径, 分集进度)
        临时目录.replace(最终目录)
        _报告(回调, 1.0, f"av{稿件号} 的 {总数} 个分集已重建")
        return 最终目录
    except Exception:
        文件工具.rmtree(临时目录, ignore_errors=True)
        raise


def 重建缓存目录(
    归档: 恢复归档,
    输出根目录: str | 路径,
    FFmpeg路径: str,
    回调: 进度回调 | None = None,
) -> 路径:
    r"""兼容原单项接口。"""
    return 重建缓存组([归档], 输出根目录, FFmpeg路径, 回调)


def _执行ADB(
    ADB路径: str,
    序列号: str,
    *参数: str,
    检查: bool = True,
    超时秒数: float = 1800,
) -> 子进程.CompletedProcess:
    return _执行命令(
        [ADB路径, "-s", 序列号, *参数],
        超时秒数=超时秒数,
        检查=检查,
    )


def _远端存在(ADB路径: str, 序列号: str, 远端路径: str) -> bool:
    结果 = _执行ADB(
        ADB路径,
        序列号,
        "shell",
        f"test -e {命令行转义.quote(远端路径)}",
        检查=False,
        超时秒数=15,
    )
    return 结果.returncode == 0


def _远端MD5(ADB路径: str, 序列号: str, 远端路径: str) -> str:
    结果 = _执行ADB(
        ADB路径,
        序列号,
        "shell",
        f"md5sum {命令行转义.quote(远端路径)}",
        超时秒数=60,
    )
    MD5值 = 结果.stdout.strip().split()[0].lower() if 结果.stdout.strip() else ""
    if not 正则.fullmatch(r"[0-9a-f]{32}", MD5值):
        raise RuntimeError(f"手机端无法计算 MD5: {远端路径}")
    return MD5值


def 导入缓存到手机(
    缓存目录: str | 路径,
    ADB路径: str,
    序列号: str,
    包名: str,
    缓存布局: str,
    回调: 进度回调 | None = None,
) -> str:
    r"""先上传到 Download 暂存区并逐文件校验，再原子移动到应用缓存目录。"""
    本地目录 = 路径(缓存目录)
    if not 本地目录.is_dir() or not 本地目录.name.isdigit():
        raise RuntimeError("待导入目录必须是以数字 avid 命名的已还原缓存")
    if not _安卓包名格式.fullmatch(包名):
        raise RuntimeError(f"无效的 Android 包名: {包名}")
    if 缓存布局 not in _允许的缓存布局:
        raise RuntimeError(f"不支持的缓存布局: {缓存布局}")

    设备状态 = _执行ADB(ADB路径, 序列号, "get-state", 超时秒数=15)
    if 设备状态.stdout.strip() != "device":
        raise RuntimeError(f"ADB 设备未就绪: {序列号}")
    包检查 = _执行ADB(
        ADB路径, 序列号, "shell", "pm", "path", 包名, 检查=False, 超时秒数=15
    )
    if 包检查.returncode != 0 or not 包检查.stdout.strip().startswith("package:"):
        raise RuntimeError(f"目标设备未安装对应客户端: {包名}")

    远端根目录 = f"/sdcard/Android/data/{包名}/{缓存布局}"
    远端最终目录 = f"{远端根目录}/{本地目录.name}"
    if not _远端存在(ADB路径, 序列号, 远端根目录):
        raise RuntimeError(f"手机缓存目录不存在: {远端根目录}")
    if _远端存在(ADB路径, 序列号, 远端最终目录):
        raise 缓存已存在错误(f"手机中已存在 av{本地目录.name}，为避免覆盖已停止导入")

    暂存根目录 = f"/sdcard/Download/MyBiOutRestore-{唯一编号.uuid4().hex}"
    暂存缓存目录 = f"{暂存根目录}/{本地目录.name}"
    已移动到最终目录 = False
    try:
        _报告(回调, 0.64, "上传缓存到手机暂存区")
        _执行ADB(
            ADB路径,
            序列号,
            "shell",
            f"mkdir -p {命令行转义.quote(暂存根目录)}",
            超时秒数=30,
        )
        _执行ADB(ADB路径, 序列号, "push", str(本地目录), f"{暂存根目录}/")

        本地文件列表 = sorted(文件路径 for 文件路径 in 本地目录.rglob("*") if 文件路径.is_file())
        if not 本地文件列表:
            raise RuntimeError("还原目录中没有可导入的文件")
        for 序号, 本地文件 in enumerate(本地文件列表, start=1):
            相对路径 = 本地文件.relative_to(本地目录).as_posix()
            远端文件 = f"{暂存缓存目录}/{相对路径}"
            if _远端MD5(ADB路径, 序列号, 远端文件) != _文件MD5(本地文件):
                raise RuntimeError(f"上传校验失败: {相对路径}")
            _报告(回调, 0.68 + 0.12 * 序号 / len(本地文件列表), f"校验上传文件 {序号}/{len(本地文件列表)}")

        _报告(回调, 0.82, "停止目标客户端并写入缓存")
        _执行ADB(ADB路径, 序列号, "shell", "am", "force-stop", 包名, 超时秒数=30)
        if _远端存在(ADB路径, 序列号, 远端最终目录):
            raise 缓存已存在错误("导入期间目标缓存已出现，为避免覆盖已停止导入")
        _执行ADB(
            ADB路径,
            序列号,
            "shell",
            f"mv {命令行转义.quote(暂存缓存目录)} {命令行转义.quote(远端最终目录)}",
            超时秒数=120,
        )
        已移动到最终目录 = True

        条目文件 = next(本地目录.rglob("entry.json"), None)
        if 条目文件:
            时间戳 = _读取JSON(条目文件).get("time_update_stamp")
            if isinstance(时间戳, (int, float)) and 时间戳 > 0:
                时间文本 = 日期时间.fromtimestamp(时间戳 / 1000).strftime("%Y%m%d%H%M.%S")
                远端文件列表 = " ".join(
                    命令行转义.quote(f"{远端最终目录}/{文件路径.relative_to(本地目录).as_posix()}")
                    for 文件路径 in 本地文件列表
                )
                _执行ADB(
                    ADB路径,
                    序列号,
                    "shell",
                    f"touch -t {时间文本} {远端文件列表}",
                    检查=False,
                    超时秒数=60,
                )

        for 序号, 本地文件 in enumerate(本地文件列表, start=1):
            相对路径 = 本地文件.relative_to(本地目录).as_posix()
            远端文件 = f"{远端最终目录}/{相对路径}"
            if _远端MD5(ADB路径, 序列号, 远端文件) != _文件MD5(本地文件):
                raise RuntimeError(f"手机最终校验失败: {相对路径}")
            _报告(回调, 0.84 + 0.15 * 序号 / len(本地文件列表), f"校验手机缓存 {序号}/{len(本地文件列表)}")

        _报告(回调, 1.0, "恢复与导入完成")
        return 远端最终目录
    finally:
        try:
            if not 已移动到最终目录:
                _执行ADB(
                    ADB路径,
                    序列号,
                    "shell",
                    f"rm -rf {命令行转义.quote(暂存根目录)}",
                    检查=False,
                    超时秒数=60,
                )
            else:
                _执行ADB(
                    ADB路径,
                    序列号,
                    "shell",
                    f"rmdir {命令行转义.quote(暂存根目录)}",
                    检查=False,
                    超时秒数=30,
                )
        except Exception:
            pass
