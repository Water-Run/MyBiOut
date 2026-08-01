r"""
MyBiOut! 绿色版一键打包脚本（独立维护入口）

用法:
    python 打包.py          # 正常打包 (本月序标甲…丑 递增)
    python 打包.py 重来     # 版本计时归零, 下次打包从本月「甲」起算
    python 打包.py 帮助

流程:
    0) 互斥锁 + 清理半成品残留；计算并写入中文版本号
    1) 安装依赖（已装则跳过升级, 加快重复打包）
    2) PyInstaller 构建（增量、无 collect-all 全量收集）
    3) 组装绿色目录（先删旧绿包；工具/脱敏配置强制校验）
    4) 调用本机 rar 命令行打 .rar 发布包（PATH 上的 rar / 任意提供 Rar 的安装均可）
       包内: MyBiOut!/ + README.txt + LICENSE；写出到 打包结果/
    5) 收尾：裁剪过旧发布包

中文版本轨: 年月 + 月内序标 (甲乙丙丁戊己庚辛壬癸子丑, 每月最多 12 包)。
超过 12 个会提示「受不了版本号溢出来了....」并坠机退出; 可用「重来」从甲重新计。
发布包名例: 「MyBiOut! 二六〇七甲.rar」(名称中空格 / ! 均保留)。

终端 TUI（有交互控制台时）:
    开场 10→1 → MyBiOut! / 即将开始（快速语法结构检查）
    直升机: 起飞 → 按进度来回巡航 → 成功降落 / 失败坠机
    结算页「搞定了!」含版本与耗时

失败时版本号回滚；中途崩溃留下的 .part / 临时绿包会在下次开工清理。
"""

from __future__ import annotations

import configparser as 配置解析器
import math as 数学
import os as 操作系统
import random as 随机
import shutil as 文件工具
import socket as 套接字
import subprocess as 子进程
import sys as 系统
import threading as 线程
import time as 时间
from contextlib import suppress as 忽略异常
from dataclasses import dataclass as 数据类
from dataclasses import field as 字段
from datetime import date as 日期
from datetime import datetime as 日期时间
from pathlib import Path as 路径

# ---------- 路径与常量 ----------

工程根目录: 路径 = 路径(__file__).resolve().parent
程序包目录: 路径 = 工程根目录 / "mybiout"
版本文件路径: 路径 = 程序包目录 / "version.txt"
产物显示名: str = "MyBiOut!"
绿色目录名: str = "MyBiOut-green"
_CLR远程加载配置: str = """<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <runtime>
    <loadFromRemoteSources enabled="true" />
  </runtime>
</configuration>
"""
_窗口冒烟状态环境键: str = "MYBIOOUT_WINDOW_SMOKE_STATUS"
# 最终 .rar 直接落在工程根下的本目录 (gitignore 排除, 勿放 dist/)
发布目录名: str = "打包结果"
构建缓存目录名: str = "build"
产物输出目录名: str = "dist"
# 发布目录中最多保留的历史 rar 个数（含本次；防 打包结果/ 无限膨胀）
发布包保留个数: int = 5
# Windows 删除被占用目录时的重试
删除重试次数: int = 6
删除重试间隔秒: float = 0.35
# 构建产物实际目录 (预清理失败时可能使用临时名)
_实际产物目录: 路径 | None = None

# 发布配置必须清空的凭证键（大小写不敏感）
_凭证键名: frozenset[str] = frozenset(
    {
        "sessdata",
        "key",
        "cookie",
        "token",
        "password",
        "secret",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "authorization",
    }
)
# 发布配置不得带打包机本机路径的键
_本机路径键名: frozenset[str] = frozenset(
    {
        "bilibili_pc_cache_path",
    }
)
_跳过拷贝目录名: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".git",
        ".svn",
        ".hg",
        ".idea",
        ".vscode",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
    }
)
_跳过拷贝文件名: frozenset[str] = frozenset(
    {
        ".ds_store",
        "thumbs.db",
        "desktop.ini",
        ".pack.lock",
    }
)
_跳过拷贝后缀: frozenset[str] = frozenset(
    {
        ".pyc",
        ".pyo",
        ".part",
        ".tmp",
        ".partial",
        ".lock",
        ".bak",
    }
)

依赖列表: list[str] = [
    "fastapi",
    "uvicorn[standard]",
    "httpx",
    "pywebview",
    "pyinstaller",
    "qrcode",
]

内嵌数据项: list[tuple[路径, str]] = [
    (程序包目录 / "pages", "mybiout/pages"),
    (程序包目录 / "assets", "mybiout/assets"),
    (程序包目录 / "version.txt", "mybiout"),
    (程序包目录 / "bin" / "BullshitGenerator", "mybiout/bin/BullshitGenerator"),
]

隐藏导入列表: list[str] = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "mybiout",
    "mybiout.main",
    "mybiout.pages.apis",
    "mybiout.pages.utils",
    "mybiout.pages.bbdown.bbdown",
    "mybiout.pages.localout.localout",
    "mybiout.pages.mdout.mdout",
    "mybiout.pages.man.man",
    "mybiout.pages.ohmyconfig.ohmyconfig",
]

# 不再 --collect-all（极慢）; 靠 hidden-import 即可, 缺模块再补

# 进度规划 (按真实耗时权重, 总和 1.0)
#   版本  极短
#   依赖  首次稍久 / 二次很快
#   构建  绝对大头 (PyInstaller)
#   组装  拷贝文件
#   压缩  zip
# 区间为 [起, 止), 最后一段闭到 1.0
阶段表: tuple[tuple[str, float, float, str], ...] = (
    # 键, 起, 止, 短名(进度条用)
    ("版本", 0.00, 0.05, "版本"),
    ("依赖", 0.05, 0.15, "依赖"),
    ("构建", 0.15, 0.78, "构建"),  # ~63% 条长, 匹配最久步骤
    ("组装", 0.78, 0.90, "组装"),
    ("压缩", 0.90, 1.00, "压缩"),
)
阶段进度: dict[str, float] = {键: 止 for 键, _起, 止, _名 in 阶段表}
阶段短名: dict[str, str] = {键: 名 for 键, _起, _止, 名 in 阶段表}
阶段序: dict[str, int] = {键: i + 1 for i, (键, *_ ) in enumerate(阶段表)}
阶段总数: int = len(阶段表)

# 巡航往返半程次数（进度 0→1 内完成若干次来回, 最后再降落）
_巡航半程数: int = 5


def 查阶段(进度: float) -> tuple[int, str, float, float, str]:
    r"""由进度值反查 (序号1-based, 键, 起, 止, 短名)。"""
    p = max(0.0, min(1.0, 进度))
    for i, (键, 起, 止, 名) in enumerate(阶段表):
        if p < 止 or i == len(阶段表) - 1:
            return i + 1, 键, 起, 止, 名
    键, 起, 止, 名 = 阶段表[-1]
    return len(阶段表), 键, 起, 止, 名


def 阶段区间(键: str) -> tuple[float, float]:
    for k, 起, 止, _名 in 阶段表:
        if k == 键:
            return 起, 止
    return 0.0, 1.0

# ---------- 进度状态 ----------


@数据类(slots=True)
class 打包进度:
    r"""
    打包流水线与 TUI 共享的进度状态。

    进度必须来自真实工作量 (包个数 / 文件数 / 目录体积), 禁止无依据假爬。
      目标进度 — [0,1] 单调不减
      阶段键   — 版本/依赖/构建/组装/压缩
      文案     — 当前动作
      明细     — 可度量信息, 如 "3/6 fastapi" / "156 MB" / "120/400 文件"
    """

    锁: 线程.Lock = 字段(default_factory=线程.Lock)
    目标进度: float = 0.0
    文案: str = "准备中…"
    明细: str = ""
    阶段键: str = "版本"
    旧版本: str = "〇〇〇〇甲"
    新版本: str = "〇〇〇〇甲"
    已结束: bool = False
    已成功: bool = False
    失败原因: str = ""
    绿色根: 路径 | None = None
    归档: 路径 | None = None
    归档大小兆: float = 0.0
    纯文本: bool = True
    开始时刻: float = 0.0
    耗时秒: float = 0.0
    阶段切入时刻: float = 0.0
    # 当前计量 (可选, 供进度条右侧)
    计量当前: int = 0
    计量总共: int = 0

    def 打点开始(自身) -> None:
        with 自身.锁:
            自身.开始时刻 = 时间.monotonic()
            自身.阶段切入时刻 = 自身.开始时刻

    def _刷新耗时(自身) -> None:
        if 自身.开始时刻 > 0:
            自身.耗时秒 = max(0.0, 时间.monotonic() - 自身.开始时刻)

    def 更新(
        自身,
        进度: float,
        文案: str,
        *,
        阶段: str | None = None,
        明细: str | None = None,
        计量当前: int | None = None,
        计量总共: int | None = None,
    ) -> None:
        with 自身.锁:
            新 = max(0.0, min(1.0, 进度))
            if 新 < 自身.目标进度:
                新 = 自身.目标进度
            自身.目标进度 = 新
            自身.文案 = 文案
            if 明细 is not None:
                自身.明细 = 明细
            if 计量当前 is not None:
                自身.计量当前 = 计量当前
            if 计量总共 is not None:
                自身.计量总共 = 计量总共
            if 阶段 is not None and 阶段 != 自身.阶段键:
                自身.阶段键 = 阶段
                自身.阶段切入时刻 = 时间.monotonic()
            elif 阶段 is None:
                _序, 键, _a, _b, _名 = 查阶段(新)
                if 键 != 自身.阶段键:
                    自身.阶段键 = 键
                    自身.阶段切入时刻 = 时间.monotonic()

    def 进入阶段(
        自身,
        键: str,
        文案: str,
        *,
        段内: float = 0.0,
        明细: str = "",
        计量当前: int = 0,
        计量总共: int = 0,
    ) -> None:
        起, 止 = 阶段区间(键)
        段内 = max(0.0, min(0.99, 段内))
        进度 = 起 + (止 - 起) * 段内
        自身.更新(
            进度,
            文案,
            阶段=键,
            明细=明细,
            计量当前=计量当前,
            计量总共=计量总共,
        )

    def 完成阶段(自身, 键: str, 文案: str | None = None, *, 明细: str = "") -> None:
        _起, 止 = 阶段区间(键)
        自身.更新(止, 文案 or f"{阶段短名.get(键, 键)}完成", 阶段=键, 明细=明细)

    def 标记成功(
        自身,
        *,
        绿色根: 路径,
        归档: 路径,
        大小兆: float,
    ) -> None:
        with 自身.锁:
            自身._刷新耗时()
            自身.目标进度 = 1.0
            自身.阶段键 = "压缩"
            自身.文案 = "搞定了!"
            自身.明细 = f"产出 {大小兆:.1f} MB"
            自身.绿色根 = 绿色根
            自身.归档 = 归档
            自身.归档大小兆 = 大小兆
            自身.已成功 = True
            自身.已结束 = True

    def 标记失败(自身, 原因: str) -> None:
        with 自身.锁:
            自身._刷新耗时()
            自身.失败原因 = 原因 or "未知错误"
            自身.已成功 = False
            自身.已结束 = True

    def 快照(自身) -> tuple[float, str, str, str, bool, bool, str]:
        r"""目标进度, 文案, 阶段键, 明细, 已结束, 已成功, 失败原因。"""
        with 自身.锁:
            return (
                自身.目标进度,
                自身.文案,
                自身.阶段键,
                自身.明细,
                自身.已结束,
                自身.已成功,
                自身.失败原因,
            )


def 目录体积字节(根: 路径) -> int:
    if not 根.exists():
        return 0
    总 = 0
    try:
        if 根.is_file():
            return 根.stat().st_size
        for p in 根.rglob("*"):
            if p.is_file():
                try:
                    总 += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return 总


def _应跳过拷贝路径(路径点: 路径) -> bool:
    r"""过滤缓存、VCS、半成品、系统垃圾，避免进绿包/zip。"""
    if any(部分 in _跳过拷贝目录名 for 部分 in 路径点.parts):
        return True
    名小 = 路径点.name.lower()
    if 名小 in _跳过拷贝文件名:
        return True
    后缀 = 路径点.suffix.lower()
    if 后缀 in _跳过拷贝后缀:
        return True
    # 半成品压缩包
    if (
        名小.endswith(".zip.part")
        or 名小.endswith(".zip.tmp")
        or 名小.endswith(".rar.part")
        or 名小.endswith(".rar.tmp")
        or 名小.endswith(".partial")
    ):
        return True
    return False


def 列举待拷文件(根: 路径) -> list[路径]:
    if not 根.is_dir():
        return []
    出: list[路径] = []
    for p in 根.rglob("*"):
        if not p.is_file():
            continue
        if _应跳过拷贝路径(p):
            continue
        出.append(p)
    return 出


def 安全删除文件(目标: 路径, *, 说明: str = "") -> None:
    if not 目标.exists():
        return
    最后: BaseException | None = None
    for 次 in range(删除重试次数):
        try:
            目标.unlink()
            return
        except OSError as 异常:
            最后 = 异常
            时间.sleep(删除重试间隔秒 * (次 + 1))
    附加 = f"\n  {说明}" if 说明 else ""
    失败退出(
        f"无法删除文件: {目标}\n"
        f"  原因: {最后}\n"
        f"  常见原因: 文件被占用（资源管理器预览、杀毒、未关闭的安装包）。请关闭占用后重试。"
        f"{附加}"
    )


def 安全移除树(目标: 路径, *, 说明: str = "") -> None:
    if not 目标.exists():
        return
    最后: BaseException | None = None
    for 次 in range(删除重试次数):
        try:
            文件工具.rmtree(目标)
            return
        except OSError as 异常:
            最后 = 异常
            时间.sleep(删除重试间隔秒 * (次 + 1))
    附加 = f"\n  {说明}" if 说明 else ""
    失败退出(
        f"无法删除目录: {目标}\n"
        f"  原因: {最后}\n"
        f"  常见原因: 绿色版 exe 仍在运行、资源管理器打开该目录、杀毒扫描占用。\n"
        f"  请先关闭 MyBiOut! 与相关窗口后再打包。"
        f"{附加}"
    )


def _检测占用中的绿色版进程() -> str:
    r"""
    检测绿色版 exe 是否在运行（运行中的 exe 会锁住 dist 产物目录）
    :return: str: 占用提示文本, 未检测到或非 Win 返回空串
    """
    if 系统.platform != "win32":
        return ""
    try:
        结果 = 子进程.run(
            ["tasklist", "/FI", f"IMAGENAME eq {产物显示名}.exe", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        )
    except OSError:
        return ""
    for 行 in (结果.stdout or "").splitlines():
        # CSV 格式: "映像名称","PID","会话名","会话#","内存使用"
        # 兼容 tasklist 偶尔输出带空格/逗号的映像名
        if 产物显示名 not in 行:
            continue
        段列表 = [段.strip('"') for 段 in 行.split('","')]
        if len(段列表) >= 2:
            return f"检测到 {产物显示名}.exe 正在运行 (PID {段列表[1]}), 它会锁住产物目录。"
    return ""


def _终止占用中的绿色版进程() -> tuple[bool, str]:
    r"""
    无条件尝试终止运行中的绿色版 exe（强制杀进程+子进程树）。
    不做预检测——taskkill 对不存在的进程也安全返回。
    :return: (是否执行了终止, 状态消息)
    """
    if 系统.platform != "win32":
        return False, ""
    try:
        终止结果: 子进程.CompletedProcess = 子进程.run(
            ["taskkill", "/F", "/T", "/IM", f"{产物显示名}.exe"],
            check=False,
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        )
        if 终止结果.returncode == 0:
            return True, f"已终止占用中的 {产物显示名}.exe (含子进程树)"
        if 终止结果.returncode == 128:
            return False, "未找到运行中的绿色版 exe (无需终止)"
        return False, f"终止失败(taskkill 返回 {终止结果.returncode})"
    except OSError as 异常:
        return False, f"无法执行 taskkill: {异常}"


def 预清理构建产物目录(状态: 打包进度 | None = None) -> tuple[bool, str]:
    r"""
    构建前清理 dist/<产物名>。PyInstaller COLLECT 阶段会 rmtree 该目录,
    其内部删除无重试, 一旦旧 exe / 外部进程占用目录, 报难懂 traceback 且
    白等整个分析/链接阶段。

    :return: (是否清理成功, 消息) — 未成功时调用方应使用临时目录构建
    """
    产物目录: 路径 = 工程根目录 / 产物输出目录名 / 产物显示名
    if not 产物目录.exists():
        return True, ""

    _终止占用中的绿色版进程()

    最后: BaseException | None = None
    for 次 in range(12):
        if 次 > 0:
            时间.sleep(1.0 + 次 * 0.6)
            _终止占用中的绿色版进程()
        try:
            # 先递归改属性防止只读文件卡 rmtree
            for 根, 目录们, 文件们 in 操作系统.walk(产物目录, topdown=False):
                for 名 in 文件们 + 目录们:
                    (路径(根) / 名).chmod(0o777)
            文件工具.rmtree(产物目录)
            if 状态 is None or 状态.纯文本:
                打印信息(f"已清理旧产物目录: {产物目录.name}")
            return True, ""
        except OSError as 异常:
            最后 = 异常

    # rmtree 全败 — 改名绕开旧目录
    try:
        import uuid as _清理临时ID
        避开名 = 产物目录.with_name(f"{产物显示名}__old_{_清理临时ID.uuid4().hex[:8]}")
        if 避开名.exists():
            文件工具.rmtree(避开名, ignore_errors=True)
        产物目录.rename(避开名)
        _markRebootDelete(避开名)
        if 状态 is None or 状态.纯文本:
            打印信息(f"已将旧产物目录改名绕开: {避开名.name} (重启后删除)")
        return True, ""
    except OSError:
        pass

    占用提示 = _检测占用中的绿色版进程()
    消息 = f"dist/{产物显示名} 被占用, 已尝试 taskkill + rmtree ×12 + rename 均失败"
    if 占用提示:
        消息 += f" | {占用提示}"
    return False, 消息


def _markRebootDelete(路径对象: 路径) -> None:
    r"""标记文件或目录在下次重启时删除 (MOVEFILE_DELAY_UNTIL_REBOOT)"""
    if 系统.platform != "win32":
        return
    try:
        MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
        import ctypes as _清理ctypes
        _清理ctypes.windll.kernel32.MoveFileExW(str(路径对象), None, MOVEFILE_DELAY_UNTIL_REBOOT)
    except Exception:
        pass


def _路径含本机用户痕迹(值: str) -> bool:
    文本 = (值 or "").replace("/", "\\")
    小 = 文本.lower()
    if "\\users\\" in 小 or "\\home\\" in 小 or 小.startswith("~\\") or 小.startswith("~/"):
        return True
    try:
        家 = str(路径.home()).replace("/", "\\").lower()
        if 家 and 家 in 小:
            return True
    except OSError:
        pass
    return False


def 强制脱敏配置分区(
    分区表: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    r"""
    发布包配置硬约束:
    - 凭证类键一律置空
    - 本机路径键置空（避免打入打包机用户名目录）
    - 其它值若明显含 \\Users\\ 等痕迹则回落安全默认
    """
    出: dict[str, dict[str, str]] = {}
    for 分区, 键值表 in 分区表.items():
        新表: dict[str, str] = {}
        for 键, 原始 in 键值表.items():
            键小 = str(键).lower()
            值 = "" if 原始 is None else str(原始)
            if 键小 in _凭证键名 or any(
                片段 in 键小 for 片段 in ("password", "secret", "token", "credential")
            ):
                值 = ""
            elif 键小 in _本机路径键名:
                值 = ""
            elif 键小 in {"path", "folder"} and _路径含本机用户痕迹(值):
                # export.path 回落通用目录; folder 类相对名一般不含 Users
                值 = r"C:\MyBiOut!" if 键小 == "path" else ""
            elif _路径含本机用户痕迹(值) and (
                "path" in 键小 or "dir" in 键小 or "folder" in 键小 or "cache" in 键小
            ):
                值 = ""
            新表[str(键)] = 值
        出[str(分区)] = 新表
    return 出


def 获取打包互斥锁(状态: 打包进度 | None = None):
    r"""防止并发打包互相 rmtree / 写同一 zip。句柄需在 finally 中释放。"""
    if 系统.platform != "win32":
        return None
    try:
        import msvcrt as 微软运行时
    except ImportError:
        return None

    目录 = 工程根目录 / 产物输出目录名
    目录.mkdir(parents=True, exist_ok=True)
    锁路径 = 目录 / ".pack.lock"
    try:
        句柄 = open(锁路径, "a+b")  # noqa: SIM115
    except OSError as 异常:
        说明 = f"无法创建打包锁文件 {锁路径}: {异常}"
        if 状态 and not 状态.纯文本:
            状态.标记失败(说明)
        失败退出(说明)
    try:
        句柄.seek(0)
        微软运行时.locking(句柄.fileno(), 微软运行时.LK_NBLCK, 1)
    except OSError:
        try:
            句柄.close()
        except OSError:
            pass
        说明 = (
            "检测到另一打包进程正在运行（dist/.pack.lock 被占用）。\n"
            "  请等待其结束；若确认无其它打包，可删除 dist/.pack.lock 后重试。"
        )
        if 状态 and not 状态.纯文本:
            状态.标记失败(说明.replace("\n", " "))
        失败退出(说明)
    try:
        句柄.seek(0)
        句柄.truncate()
        句柄.write(f"pid={操作系统.getpid()}\n".encode("utf-8"))
        句柄.flush()
    except OSError:
        pass
    return 句柄


def 释放打包互斥锁(句柄) -> None:
    if 句柄 is None:
        return
    try:
        import msvcrt as 微软运行时

        句柄.seek(0)
        微软运行时.locking(句柄.fileno(), 微软运行时.LK_UNLCK, 1)
    except Exception:  # noqa: BLE001
        pass
    try:
        句柄.close()
    except OSError:
        pass


def 发布包基名(版本: str) -> str:
    r"""
    发布包主文件名 (无后缀)。空格与「!」均保留, 例: MyBiOut! 二六〇七甲
    """
    return f"{产物显示名} {版本}"


def 是否发布包文件(路径点: 路径) -> bool:
    r"""识别发布目录内的正式包: 「MyBiOut! <版本>.rar」; 兼容旧「MyBiOut!-<版本>.rar」。"""
    if not 路径点.is_file():
        return False
    if 路径点.suffix.lower() not in {".rar", ".zip"}:
        return False
    名 = 路径点.name
    return 名.startswith(f"{产物显示名} ") or 名.startswith(f"{产物显示名}-")


def 发布目录路径() -> 路径:
    r"""最终 rar 输出目录: 工程根/打包结果 (不在 dist 下)。"""
    return 工程根目录 / 发布目录名


def 清理打包残留(
    状态: 打包进度 | None = None,
    *,
    阶段: str = "开工",
    保留版本: str | None = None,
) -> None:
    r"""
    开工: 清半成品 (.part / 临时绿包), 避免上次崩溃污染。
    收尾: 再清半成品, 并按 mtime 裁剪过旧 rar（保留 发布包保留个数）。
    不删 build/ 与 PyInstaller onedir（增量构建需要）。
    """
    产物根 = 工程根目录 / 产物输出目录名
    发布目录 = 发布目录路径()
    绿包 = 产物根 / 绿色目录名

    if 状态 is None or 状态.纯文本:
        打印信息(f"清理打包残留（{阶段}）…")

    # 临时绿包目录（若将来/异常留下）
    for 后缀 in (".tmp", ".new", ".partial", ".staging"):
        安全移除树(路径(str(绿包) + 后缀), 说明=f"清理临时绿包 {后缀}")

    if 发布目录.is_dir():
        for 文件 in list(发布目录.iterdir()):
            if not 文件.is_file():
                continue
            名小 = 文件.name.lower()
            if (
                名小.endswith(".part")
                or 名小.endswith(".tmp")
                or 名小.endswith(".partial")
                or 名小.endswith(".zip.part")
                or 名小.endswith(".rar.part")
            ):
                try:
                    文件.unlink()
                    if 状态 is None or 状态.纯文本:
                        打印信息(f"已删除半成品: {文件.name}")
                except OSError:
                    pass

    if 阶段 == "收尾" and 发布目录.is_dir():
        包们 = sorted(
            (p for p in 发布目录.iterdir() if 是否发布包文件(p)),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        保留 = max(1, int(发布包保留个数))
        for 旧包 in 包们[保留:]:
            if 保留版本 and 保留版本 in 旧包.name and 旧包 == 包们[0]:
                continue
            try:
                旧包.unlink()
                if 状态 is None or 状态.纯文本:
                    打印信息(f"已裁剪过旧发布包: {旧包.name}")
            except OSError as 异常:
                if 状态 is None or 状态.纯文本:
                    打印警告(f"无法删除旧包 {旧包.name}: {异常}")


# ---------- 终端基础 ----------

_控制序列引导: str = "\033["
_隐藏光标: str = f"{_控制序列引导}?25l"
_显示光标: str = f"{_控制序列引导}?25h"
_清屏: str = f"{_控制序列引导}2J{_控制序列引导}H"
_重置样式: str = f"{_控制序列引导}0m"
_加粗样式: str = f"{_控制序列引导}1m"
_进入备用屏: str = f"{_控制序列引导}?1049h"
_退出备用屏: str = f"{_控制序列引导}?1049l"
_回原点: str = f"{_控制序列引导}H"
_清行尾: str = f"{_控制序列引导}K"
_同步开: str = f"{_控制序列引导}?2026h"  # 终端同步刷新, 防闪烁
_同步关: str = f"{_控制序列引导}?2026l"

_盲文低密度: str = "⠁⠂⠄⡀⠈⠐⠠⢀"
_盲文中密度: str = "⠃⠅⠆⠉⠊⠌⠑⠒⠔⡁⡂⡄⡈⡐⡠⢁⢂⢄⢈⢐⢠⣀"
_盲文高密度: str = "⠿⡿⢿⣿⣾⣽⣻⣷⣯⣟⡷⡯⡟⠷⠯⠟⣶⣵⣳"
_闪光字符: str = "✦✧⋆˚✩✫✬✮✰⊹✵✺❖"
_最大粒子数: int = 280

# 传统构型直升机 (半角 ASCII) — 侧视按真实布局精修对齐:
#
#   主旋翼: 短, 动态对齐座舱中心 (绝不整机居中)
#   座舱:   短粗 4 列 [oo] + 机头
#   尾梁:   细长 11 列单线 (约 2.7× 座舱)
#   尾部:   垂尾 T + 尾桨 ?
#   起落撬: 仅座舱投影下
#
# 朝右:
#              --*--
#                |
#   ?T-----------+[oo]>
#                 /##\
#                //  \\
#
# 约定: '?'=尾桨  'T'=垂尾  '-'=尾梁  '+'=梁舱衔接  '[oo]'=座舱  '>'/'<'=机头
_短旋翼帧: tuple[str, ...] = (
    " --*-- ",
    "--*=*--",
    "-*+++*-",
    "--*=*--",
)
_尾桨帧: tuple[str, ...] = ("|", "/", "-", "\\")
# 行0 占位(桅杆单独画); 行1 主轮廓; 行2 舱肚; 行3 撬 — 列与座舱严格对齐
_机身朝右: tuple[str, ...] = (
    "                        ",
    "?T-----------+[oo]>     ",
    r"              /##\      ",
    r"             //  \\     ",
)
_机身朝左: tuple[str, ...] = (
    "                        ",
    "     <[oo]+-----------T?",
    r"      /##\              ",
    r"     //  \\             ",
)
_机身宽统一: int = max(max(len(x) for x in _机身朝右), max(len(x) for x in _机身朝左))
_机身朝右 = tuple(行.ljust(_机身宽统一)[:_机身宽统一] for 行 in _机身朝右)
_机身朝左 = tuple(行.ljust(_机身宽统一)[:_机身宽统一] for 行 in _机身朝左)
_直升机宽度: int = _机身宽统一
_直升机高度: int = 1 + max(len(_机身朝右), len(_机身朝左))  # +1 主旋翼行
_尾梁字符: frozenset[str] = frozenset("-_")
_座舱字符: frozenset[str] = frozenset("[]oO#")
_起落撬字符: frozenset[str] = frozenset("/\\")
_垂尾字符: frozenset[str] = frozenset("T")


def _座舱中心列(机身行: str) -> int:
    r"""侧视主轮廓行上座舱中心 (相对机身左缘的列索引)。"""
    起 = 机身行.find("[")
    止 = 机身行.find("]", 起 + 1) if 起 >= 0 else -1
    if 起 >= 0 and 止 > 起:
        return (起 + 止) // 2
    for 标记 in ("o", "O", "#"):
        i = 机身行.find(标记)
        if i >= 0:
            return i
    return max(0, len(机身行) // 2)


def _座舱列范围(机身行: str) -> tuple[int, int]:
    r"""返回座舱 [起, 止) 列范围 (含方括号)。"""
    起 = 机身行.find("[")
    止 = 机身行.find("]", 起 + 1) if 起 >= 0 else -1
    if 起 >= 0 and 止 > 起:
        return 起, 止 + 1
    return 0, 0

# MyBiOut! 两套纯 ASCII 标题 (禁止全角块字符, 避免列偏移)
# 1) 开场/快速检查: 字母块, 结构清晰、检查页停留易扫读
_检查标题字形: tuple[str, ...] = (
    "M   M         BBBBB  i   OOO          t  !",
    "MM MM  y   y  B   B     O   O  u  u  ttt !",
    "M M M   y y   BBBB   i  O   O  u  u   t  !",
    "M   M    y    B   B  i  O   O  u  u   t   ",
    "M   M    y    BBBBB  i   OOO    uu    t  !",
)
# 2) 结算页: 高密度轮廓字 (FIGlet standard 风格), 仪式感/远距可读
#    等宽补齐; 末行独立 '!' 与主字形右缘对齐
_结算标题字形: tuple[str, ...] = (
    r" __  __        ____  _  ___         _   _ ",
    r"|  \/  |_   _ | __ )(_)/ _ \ _   _ | |_( )",
    r"| |\/| | | | ||  _ \| | | | | | | || __| |",
    r"| |  | | |_| || |_) | | |_| | |_| || |_| |",
    r"|_|  |_| \__, ||____/|_|\___/ \__,_| \__|_|",
    r"         |___/                            !",
)
_检查标题宽度: int = max(len(行) for 行 in _检查标题字形)
_结算标题宽度: int = max(len(行) for 行 in _结算标题字形)
_检查标题字形 = tuple(行.ljust(_检查标题宽度) for 行 in _检查标题字形)
_结算标题字形 = tuple(行.ljust(_结算标题宽度) for 行 in _结算标题字形)
# 兼容旧名: 默认指向检查页字形 (开场倒计时/快速检查)
_标题字形 = _检查标题字形
_标题宽度 = _检查标题宽度

# 震撼倒计时用大号数字 — 仅 ASCII '#', 与绘制列一一对应
_大数字字形: dict[str, tuple[str, ...]] = {
    "0": (
        "  #####  ",
        " ##   ## ",
        " ##   ## ",
        " ##   ## ",
        " ##   ## ",
        " ##   ## ",
        "  #####  ",
    ),
    "1": (
        "   ##    ",
        "  ###    ",
        "   ##    ",
        "   ##    ",
        "   ##    ",
        "   ##    ",
        " ######  ",
    ),
    "2": (
        "  #####  ",
        " ##   ## ",
        "      ## ",
        "   ####  ",
        "  ##     ",
        " ##      ",
        " ####### ",
    ),
    "3": (
        "  #####  ",
        " ##   ## ",
        "      ## ",
        "   ####  ",
        "      ## ",
        " ##   ## ",
        "  #####  ",
    ),
    "4": (
        " ##   ## ",
        " ##   ## ",
        " ##   ## ",
        " ####### ",
        "      ## ",
        "      ## ",
        "      ## ",
    ),
    "5": (
        " ####### ",
        " ##      ",
        " ##      ",
        " ######  ",
        "      ## ",
        " ##   ## ",
        "  #####  ",
    ),
    "6": (
        "  #####  ",
        " ##   ## ",
        " ##      ",
        " ######  ",
        " ##   ## ",
        " ##   ## ",
        "  #####  ",
    ),
    "7": (
        " ####### ",
        "      ## ",
        "     ##  ",
        "    ##   ",
        "   ##    ",
        "  ##     ",
        "  ##     ",
    ),
    "8": (
        "  #####  ",
        " ##   ## ",
        " ##   ## ",
        "  #####  ",
        " ##   ## ",
        " ##   ## ",
        "  #####  ",
    ),
    "9": (
        "  #####  ",
        " ##   ## ",
        " ##   ## ",
        "  ###### ",
        "      ## ",
        " ##   ## ",
        "  #####  ",
    ),
}

_倒计时样式表: tuple[str, ...] = (
    "脉冲放大",
    "盲文溶出",
    "闪光雨",
    "震颤冲击",
    "涟漪扫屏",
    "粒子环爆",
    "渐变切割",
)


@数据类(frozen=True, slots=True)
class _主题:
    渐变甲: tuple[int, int, int]
    渐变乙: tuple[int, int, int]
    辅色组: tuple[tuple[int, int, int], ...]
    直升机色: tuple[int, int, int]
    星空色组: tuple[tuple[int, int, int], ...]


_会话主题: _主题 | None = None

_主题表: tuple[_主题, ...] = (
    _主题(
        (0, 255, 255),
        (255, 0, 255),
        ((255, 255, 0), (0, 255, 200), (255, 100, 255)),
        (0, 255, 220),
        ((60, 60, 100), (80, 50, 120), (50, 70, 110)),
    ),
    _主题(
        (255, 220, 50),
        (255, 30, 0),
        ((255, 255, 120), (255, 180, 50), (255, 100, 20)),
        (255, 210, 70),
        ((100, 60, 30), (120, 80, 20), (80, 50, 25)),
    ),
    _主题(
        (0, 255, 128),
        (100, 0, 255),
        ((200, 255, 200), (160, 220, 255), (180, 100, 255)),
        (0, 255, 190),
        ((30, 80, 60), (40, 60, 100), (50, 50, 90)),
    ),
    _主题(
        (251, 114, 153),
        (0, 174, 236),
        ((255, 200, 220), (120, 215, 255), (255, 160, 190)),
        (251, 114, 153),
        ((80, 40, 55), (30, 60, 90), (60, 45, 70)),
    ),
    _主题(
        (0, 210, 120),
        (255, 215, 0),
        ((200, 255, 160), (255, 240, 120), (80, 255, 180)),
        (0, 230, 130),
        ((30, 80, 40), (60, 70, 20), (40, 90, 50)),
    ),
    _主题(
        (0, 80, 255),
        (0, 255, 200),
        ((100, 200, 255), (0, 255, 190), (80, 140, 255)),
        (0, 180, 255),
        ((15, 30, 70), (20, 40, 80), (10, 25, 60)),
    ),
    _主题(
        (255, 183, 197),
        (255, 105, 180),
        ((255, 228, 225), (255, 182, 193), (255, 240, 245)),
        (255, 150, 170),
        ((90, 50, 60), (80, 40, 55), (100, 60, 70)),
    ),
    _主题(
        (255, 215, 0),
        (180, 130, 50),
        ((255, 240, 150), (220, 190, 80), (255, 200, 60)),
        (255, 220, 100),
        ((50, 40, 20), (60, 50, 25), (40, 35, 18)),
    ),
)


@数据类(slots=True)
class _粒子:
    横坐标: float
    纵坐标: float
    横速度: float
    纵速度: float
    寿命: float
    最大寿命: float
    颜色: tuple[int, int, int]

    def 步进(自身, 步长: float) -> bool:
        自身.横坐标 += 自身.横速度 * 步长
        自身.纵坐标 += 自身.纵速度 * 步长
        自身.纵速度 += 3.5 * 步长
        自身.寿命 -= 步长
        return 自身.寿命 > 0

    @property
    def 字符(自身) -> str:
        比例值 = 自身.寿命 / 自身.最大寿命 if 自身.最大寿命 > 0 else 0.0
        if 比例值 > 0.6:
            return 随机.choice(_盲文高密度)
        if 比例值 > 0.25:
            return 随机.choice(_盲文中密度)
        return 随机.choice(_盲文低密度)

    @property
    def 可见颜色(自身) -> tuple[int, int, int]:
        比例值 = 自身.寿命 / 自身.最大寿命 if 自身.最大寿命 > 0 else 0.0
        return _淡化(自身.颜色, 比例值)


def _定位(行: int, 列: int) -> str:
    return f"{_控制序列引导}{行};{列}H"


def _前景色(红: int, 绿: int, 蓝: int) -> str:
    return f"{_控制序列引导}38;2;{红};{绿};{蓝}m"


def _线性插值(
    起值: tuple[int, int, int],
    止值: tuple[int, int, int],
    比例: float,
) -> tuple[int, int, int]:
    钳 = max(0.0, min(1.0, 比例))
    return (
        int(起值[0] + (止值[0] - 起值[0]) * 钳),
        int(起值[1] + (止值[1] - 起值[1]) * 钳),
        int(起值[2] + (止值[2] - 起值[2]) * 钳),
    )


def _淡化(颜色值: tuple[int, int, int], 透明度: float) -> tuple[int, int, int]:
    强度 = max(0.0, min(1.0, 透明度))
    return int(颜色值[0] * 强度), int(颜色值[1] * 强度), int(颜色值[2] * 强度)


def _单元宽(字符: str) -> int:
    r"""
    终端显示列宽 (与 Windows Terminal / Cascadia 习惯对齐):
    - ASCII → 1
    - CJK / 全角 → 2
    - 盲文、方块、装饰符等多按 1 列 (勿一律 ord>0x7F=2, 否则大字标题会错位)
    """
    if not 字符 or 字符 == "\x00":
        return 0
    码 = ord(字符)
    if 码 < 0x80:
        return 1
    if (
        0x2E80 <= 码 <= 0x9FFF
        or 0xF900 <= 码 <= 0xFAFF
        or 0xFF01 <= 码 <= 0xFF60
        or 0xFFE0 <= 码 <= 0xFFE6
        or 0x3000 <= 码 <= 0x303F
        or 0x20000 <= 码 <= 0x2FA1F
    ):
        return 2
    return 1


def _中日韩宽度(文本: str) -> int:
    return sum(_单元宽(字符) for 字符 in 文本)


def _截断显示(文本: str, 最大宽: int) -> str:
    if _中日韩宽度(文本) <= 最大宽:
        return 文本
    出 = ""
    宽 = 0
    for 字符 in 文本:
        增 = _单元宽(字符)
        if 宽 + 增 > 最大宽 - 3:
            return 出 + "..."
        出 += 字符
        宽 += 增
    return 出


def _等待任意键(提示: str = "按任意键关机…") -> None:
    r"""结束后停留, 不立刻关掉窗口/退出备用屏。提示为空时不向 stdout 打印 (TUI 帧内已画过)。"""
    if 提示:
        try:
            print()
            print(提示, end="", flush=True)
        except Exception:
            pass
    try:
        if 系统.platform == "win32":
            import msvcrt as 微软运行时

            微软运行时.getch()
            if 提示:
                try:
                    print()
                except Exception:
                    pass
            return
    except Exception:
        pass
    try:
        input(提示 or "")
    except Exception:
        时间.sleep(12.0)


def _真关机(
    *,
    绘制=None,
    冲刷=None,
    行: int = 1,
    宽度: int = 40,
    颜色: tuple[int, int, int] = (255, 90, 90),
) -> None:
    r"""
    一点点恶意编程: 打包成功按任意键后真关机。
    Windows: ``shutdown -s -t 0`` (立即关机, 无倒计时窗口可取消)。
    """
    句 = "正在关机… shutdown -s -t 0"
    if 绘制 is not None and 冲刷 is not None:
        绘制(行, 1, " " * max(1, 宽度), 颜色=颜色)
        列 = max(1, (宽度 - _中日韩宽度(句)) // 2)
        绘制(行, 列, 句, 颜色=颜色, 加粗=True)
        冲刷()
    else:
        try:
            print(句, flush=True)
        except Exception:
            pass
    时间.sleep(0.25)
    # 自动化/CI: MYBIOUT_NO_SHUTDOWN=1 跳过真关机
    if 操作系统.environ.get("MYBIOUT_NO_SHUTDOWN", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        try:
            print("[打包] MYBIOUT_NO_SHUTDOWN 已设, 跳过真关机", flush=True)
        except Exception:
            pass
        return
    if 系统.platform == "win32":
        # shell=False; -s 关机, -t 0 立即 (等同 shutdown /s /t 0)
        子进程.Popen(
            ["shutdown", "-s", "-t", "0"],
            stdin=子进程.DEVNULL,
            stdout=子进程.DEVNULL,
            stderr=子进程.DEVNULL,
            close_fds=True,
        )
    else:
        # 非 Win 不硬关机, 避免误伤开发环境
        try:
            print("非 Windows, 跳过真关机。", flush=True)
        except Exception:
            pass


def _爆发粒子(
    粒子池: list[_粒子],
    横坐标: float,
    纵坐标: float,
    数量: int,
    颜色组: tuple[tuple[int, int, int], ...],
    *,
    速度: float = 5.0,
    寿命: tuple[float, float] = (0.4, 1.2),
    散布: float = 1.0,
) -> None:
    for _ in range(数量):
        角度 = 随机.uniform(0.0, 数学.tau)
        速度绝对值 = 随机.uniform(速度 * 0.3, 速度)
        存活时间 = 随机.uniform(*寿命)
        粒子池.append(
            _粒子(
                横坐标=横坐标 + 随机.uniform(-散布, 散布),
                纵坐标=纵坐标 + 随机.uniform(-散布 * 0.3, 散布 * 0.3),
                横速度=数学.cos(角度) * 速度绝对值,
                纵速度=数学.sin(角度) * 速度绝对值 * 0.4,
                寿命=存活时间,
                最大寿命=存活时间,
                颜色=随机.choice(颜色组),
            ),
        )
    if len(粒子池) > _最大粒子数:
        del 粒子池[: len(粒子池) - _最大粒子数]


def 配置控制台编码() -> None:
    for 流 in (系统.stdout, 系统.stderr):
        if 流 is None:
            continue
        重配 = getattr(流, "reconfigure", None)
        if 重配 is None:
            continue
        try:
            重配(encoding="utf-8", errors="replace")
        except (TypeError, ValueError, OSError):
            try:
                重配(errors="replace")
            except (TypeError, ValueError, OSError):
                pass
    # Windows 控制台启用 VT 处理, 否则真彩/定位会成乱码或被忽略
    if 系统.platform == "win32":
        try:
            import ctypes

            内核 = ctypes.windll.kernel32
            句柄 = 内核.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            模式 = ctypes.c_uint32()
            if 内核.GetConsoleMode(句柄, ctypes.byref(模式)):
                内核.SetConsoleMode(句柄, 模式.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            pass


def 可否播放动画() -> bool:
    输出 = 系统.stdout
    if 输出 is None:
        return False
    try:
        if not 输出.isatty():
            return False
    except Exception:
        return False
    try:
        宽度, 高度 = 文件工具.get_terminal_size((80, 24))
    except OSError:
        return False
    return 宽度 >= 52 and 高度 >= 18


def _当前主题() -> _主题:
    global _会话主题
    if _会话主题 is None:
        _会话主题 = 随机.choice(_主题表)
    return _会话主题


def _着色(文本: str, 颜色: tuple[int, int, int] | None = None, *, 加粗: bool = False) -> str:
    if 颜色 is None and not 加粗:
        return 文本
    负载 = ""
    if 加粗:
        负载 += _加粗样式
    if 颜色 is not None:
        负载 += _前景色(*颜色)
    return f"{负载}{文本}{_重置样式}"


def 打印标题(文本: str) -> None:
    主题 = _当前主题()
    线 = "═" * 48
    print()
    print(_着色(f"  {线}", 主题.渐变甲, 加粗=True))
    print(_着色(f"  {文本}", 主题.渐变乙, 加粗=True))
    print(_着色(f"  {线}", 主题.渐变甲, 加粗=True))


def 打印步骤(序号: int, 总数: int, 标题: str) -> None:
    主题 = _当前主题()
    print()
    print(
        _着色(f"  [{序号}/{总数}] ", 主题.直升机色, 加粗=True)
        + _着色(标题, 主题.辅色组[序号 % len(主题.辅色组)], 加粗=True)
    )


def 打印信息(文本: str) -> None:
    print(_着色("  · ", _当前主题().辅色组[0]) + 文本)


def 打印成功(文本: str) -> None:
    print(_着色("  √ ", (80, 255, 160), 加粗=True) + _着色(文本, _当前主题().渐变甲))


def 打印警告(文本: str) -> None:
    print(_着色("  ! ", (255, 200, 80), 加粗=True) + _着色(文本, (255, 220, 120)))


def 失败退出(说明: str, 退出码: int = 1) -> None:
    print(f"\n{_着色('【失败】', (255, 90, 90), 加粗=True)}{说明}", file=系统.stderr)
    raise SystemExit(退出码)


# ---------- 进度 TUI：倒计时 / 飞行=进度 / 坠机 / 结算（全力炫技） ----------

_演出人格表: tuple[str, ...] = (
    "赛博霓虹",
    "樱吹雪",
    "深海极光",
    "熔金狂想",
    "幽灵矩阵",
    "彩虹过载",
)
_航线表: tuple[str, ...] = ("正弦", "三角", "噪声", "螺旋", "折线")
_进度条皮表: tuple[str, ...] = ("方块", "盲文", "箭头", "火焰", "点阵")
_背景层表: tuple[str, ...] = ("星尘", "矩阵雨", "极光带", "流星", "网格脉冲")


def 快速代码检查(状态回调=None) -> tuple[bool, str]:
    r"""
    倒计时结束后的快速门禁: 关键源文件 AST 语法 + 目录结构。
    总耗时压在约 2.5~3.5 秒, 便于 MyBiOut! 页停留展示。
    """
    import ast as 语法树

    开始 = 时间.monotonic()
    最短秒 = 2.8
    待检: list[路径] = [
        工程根目录 / "打包.py",
        程序包目录 / "__init__.py",
        程序包目录 / "__main__.py",
        程序包目录 / "main.py",
        程序包目录 / "pages" / "apis.py",
        程序包目录 / "pages" / "utils.py",
        程序包目录 / "pages" / "bbdown" / "bbdown.py",
        程序包目录 / "pages" / "localout" / "localout.py",
        程序包目录 / "pages" / "mdout" / "mdout.py",
        程序包目录 / "pages" / "man" / "man.py",
        程序包目录 / "pages" / "ohmyconfig" / "ohmyconfig.py",
    ]
    必备路径: list[路径] = [
        程序包目录 / "assets",
        程序包目录 / "pages" / "index.html",
        程序包目录 / "version.txt",
        程序包目录 / "bin",
    ]
    try:
        for 索引, 文件 in enumerate(待检):
            if 状态回调 is not None:
                状态回调(f"语法校对  {文件.name}  ({索引 + 1}/{len(待检)})")
            if not 文件.is_file():
                return False, f"缺少源文件: {文件}"
            文本 = 文件.read_text(encoding="utf-8")
            语法树.parse(文本, filename=str(文件))
            时间.sleep(0.04)
        for 项 in 必备路径:
            if 状态回调 is not None:
                状态回调(f"结构检查  {项.name}")
            if not 项.exists():
                return False, f"缺少路径: {项}"
            时间.sleep(0.05)
        if 状态回调 is not None:
            状态回调("结构与语法检查通过")
        while 时间.monotonic() - 开始 < 最短秒:
            时间.sleep(0.05)
        return True, "结构与语法检查通过"
    except SyntaxError as 错:
        return False, f"语法错误 {错.filename}:{错.lineno}: {错.msg}"
    except Exception as 异常:  # noqa: BLE001
        return False, f"检查失败: {异常}"


def 运行进度TUI(状态: 打包进度, *, 开工=None) -> None:
    r"""
    完整演出管线:
      1) 10→1 震撼倒计时 → MyBiOut! / 即将开始 + 快速代码检查
      2) 开工回调启动真实打包后, 直升机飞行 = 真实进度 (限速)
      3) 失败坠机 / 成功结算页
    """
    global _会话主题
    宽度, 高度 = 文件工具.get_terminal_size((80, 24))
    if 宽度 < 52 or 高度 < 18:
        raise RuntimeError("终端尺寸过小")

    主题 = 随机.choice(_主题表)
    _会话主题 = 主题
    随机源 = 随机.Random()
    人格 = 随机源.choice(_演出人格表)
    航线 = 随机源.choice(_航线表)
    进度皮 = 随机源.choice(_进度条皮表)
    背景层 = 随机源.choice(_背景层表)
    人格种子 = {
        "赛博霓虹": {"混辅": 0.35, "闪": 0.4, "速": 0.045},
        "樱吹雪": {"混辅": 0.45, "闪": 0.55, "速": 0.048},
        "深海极光": {"混辅": 0.15, "闪": 0.2, "速": 0.05},
        "熔金狂想": {"混辅": 0.3, "闪": 0.35, "速": 0.046},
        "幽灵矩阵": {"混辅": 0.2, "闪": 0.25, "速": 0.044},
        "彩虹过载": {"混辅": 0.5, "闪": 0.6, "速": 0.045},
    }[人格]
    步长 = 人格种子["速"]
    # 直升机每帧最多推进的进度, 避免目标猛跳时一闪而过 (约 8~12 秒飞完全程下限)
    进度最大步进 = 0.0048
    输出缓冲: list[str] = []
    显示进度 = 0.0
    帧号 = 0
    粒子列表: list[_粒子] = []
    流星列表: list[tuple[float, float, float, float, tuple[int, int, int]]] = []
    矩阵列: list[tuple[int, float, str]] = []
    前行 = max(3, 高度 // 4)
    前列 = 宽度 + 6
    基准行 = max(3, 高度 // 4)
    波幅 = 随机源.uniform(0.4, 1.9)
    波频 = 随机源.uniform(0.9, 3.2)
    噪声相位 = 随机源.uniform(0, 100)
    已里程碑: set[int] = set()
    里程碑点 = (10, 25, 40, 55, 70, 85, 95)

    # 帧缓冲: 列 = 显示列 (1..宽度); 宽字符占 2 列, 第二列为占位
    空单元 = (" ", None, False)
    占位单元 = ("\x00", None, False)
    帧面: list[list[tuple[str, tuple[int, int, int] | None, bool]]] = [
        [空单元 for _ in range(宽度 + 2)] for _ in range(高度 + 2)
    ]
    背景面: list[list[tuple[str, tuple[int, int, int] | None, bool]]] = [
        [空单元 for _ in range(宽度 + 2)] for _ in range(高度 + 2)
    ]

    def 帧清(目标: list | None = None) -> None:
        面 = 目标 if 目标 is not None else 帧面
        for r in range(1, 高度 + 1):
            行 = 面[r]
            for c in range(1, 宽度 + 1):
                行[c] = 空单元

    def 拷贝背景到帧() -> None:
        for r in range(1, 高度 + 1):
            帧面[r] = 背景面[r].copy()

    def 写入(文本: str) -> None:
        输出缓冲.append(文本)

    def 原始写出(文本: str) -> None:
        try:
            系统.stdout.write(文本)
            系统.stdout.flush()
        except Exception:
            pass

    def 冲刷整帧() -> None:
        r"""
        同步整帧输出:
        - CSI ?2026 同步更新 (Windows Terminal 等支持, 大幅减闪)
        - 每行精确 宽度 个显示列, 行尾 CSI K 清残影
        - 不用多余清屏, 只回原点覆盖
        """
        块: list[str] = [_同步开, _隐藏光标, _回原点]
        for r in range(1, 高度 + 1):
            行块: list[str] = []
            上行色: object = object()
            上加粗: object = object()
            显示列 = 0
            c = 1
            while c <= 宽度 and 显示列 < 宽度:
                ch, 色, 粗 = 帧面[r][c]
                if ch == "\x00":
                    c += 1
                    continue
                字宽 = _单元宽(ch) if ch else 1
                if 字宽 <= 0:
                    字宽 = 1
                if 显示列 + 字宽 > 宽度:
                    break
                if 色 != 上行色 or 粗 != 上加粗:
                    行块.append(_重置样式)
                    if 粗:
                        行块.append(_加粗样式)
                    if 色 is not None:
                        行块.append(_前景色(*色))
                    上行色, 上加粗 = 色, 粗
                行块.append(ch if ch else " ")
                显示列 += 字宽
                c += 1
            # 补齐到终端宽度, 防止短行导致下一行错位跳动
            if 显示列 < 宽度:
                if 上行色 is not None or 上加粗:
                    行块.append(_重置样式)
                    上行色, 上加粗 = None, False
                行块.append(" " * (宽度 - 显示列))
            行块.append(_重置样式)
            行块.append(_清行尾)
            块.append("".join(行块))
            if r < 高度:
                块.append("\r\n")
        块.append(_同步关)
        原始写出("".join(块))
        输出缓冲.clear()

    def 刷新输出() -> None:
        if 输出缓冲:
            原始写出("".join(输出缓冲))
            输出缓冲.clear()
        冲刷整帧()

    def 绘制(
        行: int,
        列: int,
        文本: str,
        颜色: tuple[int, int, int] | None = None,
        加粗: bool = False,
        *,
        面: list | None = None,
    ) -> None:
        if 行 < 1 or 行 > 高度 or 列 > 宽度:
            return
        目标 = 面 if 面 is not None else 帧面
        游 = 列
        for ch in 文本:
            if 游 > 宽度:
                break
            字宽 = _单元宽(ch)
            if 字宽 <= 0:
                continue
            if 字宽 >= 2 and 游 + 字宽 - 1 > 宽度:
                break
            目标[行][游] = (ch, 颜色, 加粗)
            if 字宽 >= 2:
                目标[行][游 + 1] = 占位单元
            游 += 字宽

    def 清行(行: int, 起列: int = 1, 止列: int | None = None, *, 面: list | None = None) -> None:
        if 行 < 1 or 行 > 高度:
            return
        目标 = 面 if 面 is not None else 帧面
        结束列 = min(止列 or 宽度, 宽度)
        for c in range(max(1, 起列), 结束列 + 1):
            目标[行][c] = 空单元

    def 全屏清() -> None:
        帧清()
        冲刷整帧()

    def _地面基准行() -> int:
        r"""地表行: 其下留给 3 行进度 HUD, 其上为天空。"""
        return max(4, 高度 - 4)

    def 绘完整地面(*, 面: list | None = None, 进度高亮: float | None = None) -> None:
        r"""铺满整行地面 + 浅草皮, 避免跑道只有稀疏虚线。"""
        地 = _地面基准行()
        if 地 < 3:
            return
        草 = 地 - 1
        for 列 in range(1, 宽度 + 1):
            t = (列 - 1) / max(宽度 - 1, 1)
            基色 = _线性插值(主题.渐变甲, 主题.渐变乙, t)
            if 进度高亮 is not None:
                亮 = 0.35 + 0.55 * max(0.0, 1.0 - abs(t - 进度高亮) * 2.2)
                基色 = _淡化(基色, min(1.0, 亮))
            else:
                基色 = _淡化(基色, 0.55)
            # 地表实线铺满
            绘制(地, 列, "=", 颜色=基色, 面=面)
            if 草 >= 2:
                草符 = "_" if 列 % 3 else "."
                绘制(草, 列, 草符, 颜色=_淡化(主题.星空色组[列 % len(主题.星空色组)], 0.4), 面=面)

    def 重建飞行背景() -> None:
        r"""低频更新静态背景层, 飞行帧只叠直升机/进度/粒子。"""
        帧清(背景面)
        地 = _地面基准行()
        天空底 = max(2, 地 - 2)
        for i in range(max(16, 宽度 * 高度 // 70)):
            rr = 1 + (i * 37) % max(1, 天空底)
            cc = 1 + (i * 91) % 宽度
            绘制(
                rr,
                cc,
                "." if i % 3 else "+",
                颜色=主题.星空色组[i % len(主题.星空色组)],
                面=背景面,
            )
        绘完整地面(面=背景面)

    def 混色盘() -> tuple[tuple[int, int, int], ...]:
        return tuple(dict.fromkeys((*主题.辅色组, 主题.渐变甲, 主题.渐变乙, 主题.直升机色)))

    def 重绘星空(*, 混入辅色: bool = False, 密度: float = 1.0) -> None:
        数量 = int(随机源.randint(宽度 * 高度 // 38, max(2, 宽度 * 高度 // 18)) * 密度)
        for _ in range(max(1, 数量)):
            if 混入辅色 and 随机源.random() < 人格种子["混辅"]:
                色 = 随机源.choice(主题.辅色组)
                符 = 随机源.choice(_闪光字符 + _盲文中密度)
            else:
                色 = 随机源.choice(主题.星空色组)
                符 = 随机源.choice(_盲文低密度 + "·.˙*")
            绘制(随机源.randint(1, max(1, 高度 - 3)), 随机源.randint(1, 宽度), 符, 颜色=色)

    def 绘极光带(相位: float) -> None:
        带数 = 随机源.randint(2, 4)
        for b in range(带数):
            基 = 2 + int((高度 - 6) * ((b + 1) / (带数 + 1)))
            for 列 in range(1, 宽度 + 1, 随机源.randint(1, 2)):
                波 = 数学.sin(相位 * 0.07 + 列 * 0.11 + b * 1.7) * 1.8
                行 = int(基 + 波)
                if 1 <= 行 <= 高度 - 3:
                    t = 列 / 宽度
                    色 = _线性插值(主题.渐变甲, 主题.渐变乙, (t + b * 0.2) % 1.0)
                    色 = _淡化(色, 0.35 + 0.4 * abs(数学.sin(相位 * 0.05 + 列 * 0.05)))
                    绘制(行, 列, 随机源.choice("▁▂▃▄░▒" + _盲文低密度), 颜色=色)

    def 绘矩阵雨() -> None:
        nonlocal 矩阵列
        if len(矩阵列) < 宽度 // 3 and 随机源.random() < 0.35:
            矩阵列.append((随机源.randint(1, 宽度), 1.0, 随机源.choice(_盲文高密度 + "01")))
        新: list[tuple[int, float, str]] = []
        for 列, 行f, 符 in 矩阵列:
            行 = int(行f)
            if 1 <= 行 <= 高度 - 2:
                色 = _线性插值(主题.渐变甲, 主题.辅色组[列 % len(主题.辅色组)], 行 / 高度)
                绘制(行, 列, 符, 颜色=_淡化(色, 0.7))
                if 行 > 1:
                    绘制(行 - 1, 列, 随机源.choice(_盲文低密度), 颜色=_淡化(色, 0.3))
            行f += 随机源.uniform(0.4, 1.1)
            if 行f < 高度 - 1:
                新.append((列, 行f, 随机源.choice(_盲文中密度 + "01╬║")))
        矩阵列 = 新

    def 更新流星() -> None:
        nonlocal 流星列表
        if 随机源.random() < 0.08 + 人格种子["闪"] * 0.1:
            流星列表.append(
                (
                    float(随机源.randint(1, 宽度)),
                    1.0,
                    随机源.uniform(-1.2, -0.4),
                    随机源.uniform(0.6, 1.4),
                    随机源.choice(混色盘()),
                )
            )
        新流: list[tuple[float, float, float, float, tuple[int, int, int]]] = []
        for x, y, vx, vy, 色 in 流星列表:
            绘制(int(y), int(x), 随机源.choice(_闪光字符 + "-═"), 颜色=色, 加粗=True)
            ty, tx = int(y - vy), int(x - vx)
            if 1 <= ty <= 高度 and 1 <= tx <= 宽度:
                绘制(ty, tx, 随机源.choice(_盲文低密度), 颜色=_淡化(色, 0.4))
            x2, y2 = x + vx, y + vy
            if 0 < x2 < 宽度 + 2 and 0 < y2 < 高度:
                新流.append((x2, y2, vx, vy, 色))
        流星列表 = 新流

    def 绘网格脉冲(相位: float) -> None:
        步 = max(4, 宽度 // 12)
        for 列 in range(1, 宽度 + 1, 步):
            亮 = 0.15 + 0.25 * abs(数学.sin(相位 * 0.08 + 列 * 0.2))
            色 = _淡化(_线性插值(主题.星空色组[0], 主题.渐变甲, 亮), 亮)
            for 行 in range(2, 高度 - 2, 2):
                if 随机源.random() < 0.4:
                    绘制(行, 列, "│", 颜色=色)
        for 行 in range(2, 高度 - 2, max(3, 高度 // 6)):
            亮 = 0.12 + 0.2 * abs(数学.sin(相位 * 0.06 + 行))
            色 = _淡化(主题.星空色组[行 % len(主题.星空色组)], 亮)
            for 列 in range(1, 宽度 + 1, 3):
                if 随机源.random() < 0.25:
                    绘制(行, 列, "·", 颜色=色)

    def 绘背景层(相位: float) -> None:
        if 背景层 == "星尘":
            if 帧号 % 12 == 0:
                重绘星空(混入辅色=随机源.random() < 人格种子["混辅"], 密度=0.15)
        elif 背景层 == "矩阵雨":
            绘矩阵雨()
            if 帧号 % 20 == 0:
                重绘星空(密度=0.08)
        elif 背景层 == "极光带":
            if 帧号 % 2 == 0:
                绘极光带(相位)
            if 帧号 % 15 == 0:
                重绘星空(混入辅色=True, 密度=0.1)
        elif 背景层 == "流星":
            if 帧号 % 10 == 0:
                重绘星空(密度=0.12)
            更新流星()
        else:
            if 帧号 % 8 == 0:
                绘网格脉冲(相位)
            if 帧号 % 14 == 0:
                重绘星空(混入辅色=True, 密度=0.1)
        if 随机源.random() < 人格种子["闪"] * 0.15:
            更新流星()

    def 取拍主题色(拍: int, 总拍: int) -> tuple[
        tuple[int, int, int],
        tuple[int, int, int],
        tuple[int, int, int],
        tuple[tuple[int, int, int], ...],
    ]:
        t = 拍 / max(总拍 - 1, 1)
        if 人格 == "彩虹过载":
            段 = (主题.渐变甲, *主题.辅色组, 主题.渐变乙, 主题.直升机色)
            i = t * (len(段) - 1)
            i0 = int(i) % (len(段) - 1)
            主色 = _线性插值(段[i0], 段[i0 + 1], i - int(i))
            次色 = _线性插值(段[-(i0 + 1)], 段[-(i0 + 2)], i - int(i))
        else:
            主色 = _线性插值(主题.渐变甲, 主题.渐变乙, t)
            次色 = _线性插值(主题.渐变乙, 主题.渐变甲, t)
        强调 = 主题.辅色组[拍 % len(主题.辅色组)]
        粒子组 = tuple(
            dict.fromkeys((*主题.辅色组, 主题.渐变甲, 主题.渐变乙, 主题.直升机色, 主色, 强调))
        )
        return 主色, 次色, 强调, 粒子组

    def 单元格颜色(
        列比例: float,
        行比例: float,
        主色: tuple[int, int, int],
        次色: tuple[int, int, int],
        强调: tuple[int, int, int],
        *,
        模式: str = "横渐变",
    ) -> tuple[int, int, int]:
        if 模式 == "竖渐变":
            return _线性插值(主色, 次色, 行比例)
        if 模式 == "对角":
            return _线性插值(主色, 强调, (列比例 + 行比例) / 2)
        if 模式 == "强调闪":
            return 强调 if 随机源.random() < 0.2 else _线性插值(主色, 次色, 列比例)
        if 模式 == "直升机描边":
            边 = min(列比例, 1 - 列比例, 行比例, 1 - 行比例)
            return _线性插值(主题.直升机色, _线性插值(主色, 次色, 列比例), min(1.0, 边 * 4))
        if 模式 == "等离子":
            w = 0.5 + 0.5 * 数学.sin(列比例 * 数学.tau * 2 + 行比例 * 3)
            return _线性插值(_线性插值(主色, 强调, w), 次色, 行比例)
        return _线性插值(主色, 次色, 列比例)

    def 绘数字串(
        串: str,
        *,
        主色: tuple[int, int, int],
        次色: tuple[int, int, int],
        强调: tuple[int, int, int],
        盲文: bool = False,
        抖x: int = 0,
        抖y: int = 0,
        亮度: float = 1.0,
        色模式: str = "横渐变",
        缩放抖动: float = 0.0,
    ) -> None:
        def 绘一块(
            字形行: tuple[str, ...],
            左: int,
            上: int,
            主: tuple[int, int, int],
            次: tuple[int, int, int],
            强: tuple[int, int, int],
        ) -> None:
            块高 = len(字形行)
            块宽 = max(len(r) for r in 字形行)
            for 行序号, 行文本 in enumerate(字形行):
                行 = 上 + 行序号
                for 列索引, 字符 in enumerate(行文本):
                    列 = 左 + 列索引
                    if 字符 == " " or not (1 <= 列 <= 宽度 and 1 <= 行 <= 高度):
                        continue
                    色 = 单元格颜色(
                        列索引 / max(块宽 - 1, 1),
                        行序号 / max(块高 - 1, 1),
                        主,
                        次,
                        强,
                        模式=色模式,
                    )
                    色 = _淡化(色, 亮度)
                    画符 = 随机源.choice(_盲文高密度) if 盲文 else 字符
                    if 缩放抖动 and 随机源.random() < 缩放抖动:
                        画符 = 随机源.choice(_闪光字符 + 画符)
                    绘制(行, 列, 画符, 颜色=色, 加粗=True)

        if len(串) == 1:
            字形 = _大数字字形.get(串, _大数字字形["0"])
            块高, 块宽 = len(字形), max(len(r) for r in 字形)
            上边 = max(1, (高度 - 块高) // 2 + 抖y)
            左边 = max(1, (宽度 - 块宽) // 2 + 抖x)
            绘一块(字形, 左边, 上边, 主色, 次色, 强调)
            return
        字形甲 = _大数字字形.get(串[0], _大数字字形["1"])
        字形乙 = _大数字字形.get(串[1], _大数字字形["0"])
        块高 = len(字形甲)
        块宽甲 = max(len(r) for r in 字形甲)
        块宽乙 = max(len(r) for r in 字形乙)
        间距 = 2
        总宽 = 块宽甲 + 间距 + 块宽乙
        上边 = max(1, (高度 - 块高) // 2 + 抖y)
        左边 = max(1, (宽度 - 总宽) // 2 + 抖x)
        绘一块(字形甲, 左边, 上边, 主色, 强调, 次色)
        绘一块(字形乙, 左边 + 块宽甲 + 间距, 上边, 强调, 次色, 主题.直升机色)

    def 播放震撼倒计时() -> None:
        帧清()
        重绘星空(混入辅色=True, 密度=0.7)
        宣 = f"✦ {人格} · {航线}航线 · {背景层} ✦"
        绘制(
            max(1, 高度 // 2),
            max(1, (宽度 - _中日韩宽度(宣)) // 2),
            宣,
            颜色=主题.直升机色,
            加粗=True,
        )
        冲刷整帧()
        时间.sleep(0.85)

        序列 = [str(n) for n in range(10, 0, -1)] + ["GO"]
        色模式池 = ("横渐变", "竖渐变", "对角", "强调闪", "直升机描边", "等离子")

        for 拍, 内容 in enumerate(序列):
            样式 = 随机源.choice(_倒计时样式表)
            色模式 = 随机源.choice(色模式池)
            主色, 次色, 强调, 粒子组 = 取拍主题色(拍, len(序列))

            if 样式 in {"涟漪扫屏", "渐变切割", "闪光雨"}:
                行序 = list(range(1, 高度 + 1))
                if 样式 == "涟漪扫屏":
                    中 = 高度 // 2
                    行序.sort(key=lambda r: abs(r - 中))
                elif 样式 == "渐变切割" and 随机源.random() < 0.5:
                    行序.reverse()
                for i, 行 in enumerate(行序):
                    if 样式 == "闪光雨" and 随机源.random() < 0.5:
                        continue
                    for _ in range(随机源.randint(1, 3)):
                        符 = 随机源.choice(_盲文中密度 + _闪光字符 + "░▒▓")
                        t = i / max(高度, 1)
                        色 = _线性插值(
                            随机源.choice(主题.星空色组),
                            _线性插值(主色, 强调, t),
                            随机源.random(),
                        )
                        绘制(行, 随机源.randint(1, 宽度), 符, 颜色=色)
                    if i % 3 == 0:
                        刷新输出()
                        时间.sleep(0.003)

            if 内容 == "GO":
                全屏清()
                重绘星空(混入辅色=True, 密度=1.3)
                for _ in range(随机源.randint(2, 5)):
                    for __ in range(30):
                        绘制(
                            随机源.randint(1, 高度),
                            随机源.randint(1, 宽度),
                            随机源.choice(_盲文高密度 + "#@%/"),
                            颜色=随机源.choice(粒子组),
                        )
                    刷新输出()
                    时间.sleep(0.03)
                    全屏清()
                重绘星空(混入辅色=True)
                标题上 = max(2, 高度 // 2 - len(_标题字形) // 2 - 1)
                标题左 = max(1, (宽度 - _标题宽度) // 2)

                def _绘标题字(
                    *,
                    用原字: bool,
                    列过滤: set[int] | None = None,
                ) -> None:
                    for 序号, 行文本 in enumerate(_标题字形):
                        行 = 标题上 + 序号
                        if not (1 <= 行 <= 高度):
                            continue
                        for 列索引, 字符 in enumerate(行文本):
                            if 列过滤 is not None and 列索引 not in 列过滤:
                                continue
                            列 = 标题左 + 列索引
                            if not (1 <= 列 <= 宽度) or 字符 == " ":
                                continue
                            if 用原字:
                                绘字 = 字符
                                色 = _线性插值(
                                    主题.渐变甲,
                                    主题.渐变乙,
                                    列索引 / max(_标题宽度 - 1, 1),
                                )
                            else:
                                绘字 = 随机源.choice("#@%*+.")
                                色 = 主题.辅色组[列索引 % len(主题.辅色组)]
                            绘制(行, 列, 绘字, 颜色=色, 加粗=True)

                # 预填噪点 (纯 ASCII, 避免宽字符挤列)
                _绘标题字(用原字=False)
                刷新输出()
                时间.sleep(0.12)
                显现列 = list(range(_标题宽度))
                match 随机源.choice(("ltr", "rtl", "center", "random", "wave")):
                    case "rtl":
                        显现列.reverse()
                    case "center":
                        mid = _标题宽度 // 2
                        显现列.sort(key=lambda c: abs(c - mid))
                    case "random":
                        随机源.shuffle(显现列)
                    case "wave":
                        显现列.sort(key=lambda c: 数学.sin(c * 0.3) * 10 + c)
                    case _:
                        pass
                批 = max(1, _标题宽度 // 14)
                已显: set[int] = set()
                for 起 in range(0, len(显现列), 批):
                    已显.update(显现列[起 : 起 + 批])
                    _绘标题字(用原字=True, 列过滤=已显)
                    刷新输出()
                    时间.sleep(0.014)
                # 终态整幅重绘, 保证无残影/偏移
                _绘标题字(用原字=True)
                刷新输出()
                标语 = "* MyBiOut! *"
                标语行 = 标题上 + len(_标题字形) + 1
                即将行 = 标语行 + 1
                状态行文 = 标语行 + 2
                if 标语行 <= 高度:
                    游 = max(1, (宽度 - _中日韩宽度(标语)) // 2)
                    for i, ch in enumerate(标语):
                        w = _单元宽(ch) or 1
                        绘制(
                            标语行,
                            游,
                            ch,
                            颜色=_线性插值(
                                主题.直升机色,
                                主题.辅色组[i % len(主题.辅色组)],
                                i / max(len(标语) - 1, 1),
                            ),
                            加粗=True,
                        )
                        游 += w
                        刷新输出()
                        时间.sleep(0.028)
                if 即将行 <= 高度:
                    即将 = "即将开始"
                    绘制(
                        即将行,
                        max(1, (宽度 - _中日韩宽度(即将)) // 2),
                        即将,
                        颜色=主题.辅色组[0],
                        加粗=True,
                    )
                    刷新输出()

                # 礼花一轮后, 长留 MyBiOut! 页, 后台跑快速代码检查 (~2.8s+)
                for _burst in range(2):
                    环爆: list[_粒子] = []
                    _爆发粒子(
                        环爆,
                        随机源.uniform(宽度 * 0.25, 宽度 * 0.75),
                        随机源.uniform(高度 * 0.2, 高度 * 0.45),
                        随机源.randint(28, 48),
                        粒子组,
                        速度=随机源.uniform(7, 11),
                        寿命=(0.3, 1.1),
                        散布=2.0,
                    )
                    for _ in range(10):
                        环爆 = [p for p in 环爆 if p.步进(0.05)]
                        for p in 环爆:
                            pc, pr = int(p.横坐标), int(p.纵坐标)
                            if 1 <= pr <= 高度 and 1 <= pc <= 宽度:
                                绘制(pr, pc, p.字符, 颜色=p.可见颜色)
                        刷新输出()
                        时间.sleep(0.025)

                # 基础检查阶段: 并行跑代码检查 + 终止占用中的旧绿色版进程
                检查结果: list[tuple[bool, str]] = [(True, "")]
                释放结果: list[tuple[bool, str]] = [(False, "")]

                def _跑检查() -> None:
                    检查结果[0] = 快速代码检查()

                def _跑释放() -> None:
                    释放结果[0] = _终止占用中的绿色版进程()

                检查线程 = 线程.Thread(target=_跑检查, daemon=True)
                检查线程.start()
                释放线程 = 线程.Thread(target=_跑释放, daemon=True)
                释放线程.start()
                停留起点 = 时间.monotonic()
                脉冲 = 0
                while 检查线程.is_alive() or 时间.monotonic() - 停留起点 < 2.9:
                    脉冲 += 1
                    # 标题呼吸光
                    if 标语行 <= 高度 and 脉冲 % 4 == 0:
                        亮 = 0.65 + 0.35 * abs(数学.sin(脉冲 * 0.15))
                        游 = max(1, (宽度 - _中日韩宽度(标语)) // 2)
                        for i, ch in enumerate(标语):
                            w = _单元宽(ch) or 1
                            色 = _淡化(
                                _线性插值(
                                    主题.直升机色,
                                    主题.辅色组[i % len(主题.辅色组)],
                                    i / max(len(标语) - 1, 1),
                                ),
                                亮,
                            )
                            绘制(标语行, 游, ch, 颜色=色, 加粗=True)
                            游 += w
                    # 标题呼吸: 周期性整幅重绘防被礼花粒子打花
                    if 脉冲 % 8 == 0:
                        _绘标题字(用原字=True)
                    if 即将行 <= 高度 and 脉冲 % 6 == 0:
                        闪 = 0.55 + 0.45 * abs(数学.sin(脉冲 * 0.22))
                        即将 = "即将开始"
                        绘制(
                            即将行,
                            max(1, (宽度 - _中日韩宽度(即将)) // 2),
                            即将,
                            颜色=_淡化(主题.辅色组[脉冲 % len(主题.辅色组)], 闪),
                            加粗=True,
                        )
                    if 状态行文 <= 高度:
                        清行(状态行文)
                        if not 检查线程.is_alive() and 检查结果[0][0]:
                            提示 = "结构与语法检查通过 · 即将起飞"
                        elif not 检查线程.is_alive() and not 检查结果[0][0]:
                            提示 = _截断显示(f"检查告警: {检查结果[0][1]}", 宽度 - 4)
                        else:
                            提示 = "代码结构 / 语法快速校对中…"
                        绘制(
                            状态行文,
                            max(1, (宽度 - _中日韩宽度(提示)) // 2),
                            提示,
                            颜色=_淡化(主题.渐变乙, 0.9),
                        )
                    if 状态行文 + 1 <= 高度:
                        清行(状态行文 + 1)
                        释文 = ""
                        if not 释放线程.is_alive():
                            释成功, 释消息 = 释放结果[0]
                            释文 = 释消息 if 释成功 else ("· " + 释消息)
                        绘制(
                            状态行文 + 1,
                            max(1, (宽度 - _中日韩宽度(释文)) // 2),
                            释文,
                            颜色=_淡化(主题.渐变甲, 0.75),
                        )
                    # 细星尘
                    if 脉冲 % 5 == 0:
                        绘制(
                            随机源.randint(1, max(1, 标题上 - 1)),
                            随机源.randint(1, 宽度),
                            随机源.choice(_闪光字符),
                            颜色=随机源.choice(粒子组),
                        )
                    刷新输出()
                    时间.sleep(0.05)
                检查线程.join(timeout=1.0)
                释放线程.join(timeout=1.0)
                if not 检查结果[0][0]:
                    # 不阻断打包, 仅在状态行多留一瞬
                    时间.sleep(0.6)
                else:
                    时间.sleep(0.35)

                for r in range(0, max(宽度, 高度) // 2, 2):
                    for 角 in range(0, 360, 12):
                        rad = 数学.radians(角)
                        cc = int(宽度 / 2 + 数学.cos(rad) * r)
                        rr = int(高度 / 2 + 数学.sin(rad) * r * 0.55)
                        if 1 <= rr <= 高度 and 1 <= cc <= 宽度:
                            绘制(
                                rr,
                                cc,
                                随机源.choice(_盲文中密度),
                                颜色=_淡化(主题.渐变甲, 1 - r / (宽度 / 2 + 1)),
                            )
                    刷新输出()
                    时间.sleep(0.014)
                全屏清()
                重绘星空()
                刷新输出()
                continue

            数字串 = 内容

            def 画当前(**kw: object) -> None:
                模式 = kw.pop("模式", 色模式)
                绘数字串(
                    数字串,
                    主色=主色,
                    次色=次色,
                    强调=强调,
                    色模式=str(模式),
                    **kw,  # type: ignore[arg-type]
                )

            if 样式 == "脉冲放大":
                for 阶段 in range(7):
                    全屏清()
                    重绘星空(混入辅色=阶段 > 2, 密度=0.9 + 阶段 * 0.05)
                    亮 = 0.35 + 0.65 * (阶段 / 6)
                    绘数字串(
                        数字串,
                        主色=_线性插值(主色, 强调, 阶段 / 6),
                        次色=_线性插值(次色, 主题.直升机色, 阶段 / 6),
                        强调=强调,
                        盲文=阶段 < 2,
                        亮度=亮,
                        色模式=色模式,
                        缩放抖动=0.08 if 阶段 > 3 else 0,
                    )
                    刷新输出()
                    时间.sleep(0.07)
                时间.sleep(0.42)
            elif 样式 == "盲文溶出":
                全屏清()
                重绘星空(混入辅色=True)
                画当前(盲文=True, 模式="等离子")
                刷新输出()
                时间.sleep(0.28)
                for k in range(6):
                    画当前(盲文=随机源.random() < 0.45 - k * 0.05, 模式="强调闪" if k % 2 else "对角")
                    刷新输出()
                    时间.sleep(0.07)
                画当前()
                刷新输出()
                时间.sleep(0.48)
            elif 样式 == "闪光雨":
                全屏清()
                重绘星空(混入辅色=True, 密度=1.2)
                for _ in range(40):
                    绘制(
                        随机源.randint(1, 高度),
                        随机源.randint(1, 宽度),
                        随机源.choice(_闪光字符 + "*|"),
                        颜色=随机源.choice(粒子组),
                        加粗=True,
                    )
                画当前(模式="强调闪")
                刷新输出()
                时间.sleep(0.65)
            elif 样式 == "震颤冲击":
                for k in range(10):
                    全屏清()
                    重绘星空(密度=0.85)
                    闪主 = (主色, 强调, 主题.直升机色, 次色)[k % 4]
                    绘数字串(
                        数字串,
                        主色=闪主,
                        次色=次色,
                        强调=强调,
                        抖x=随机源.randint(-3, 3),
                        抖y=随机源.randint(-1, 1),
                        色模式="直升机描边" if k % 2 else 色模式,
                    )
                    刷新输出()
                    时间.sleep(0.045)
                全屏清()
                重绘星空(混入辅色=True)
                画当前()
                刷新输出()
                时间.sleep(0.48)
            elif 样式 == "粒子环爆":
                全屏清()
                重绘星空(混入辅色=True)
                画当前(模式="对角")
                环: list[_粒子] = []
                _爆发粒子(环, 宽度 / 2, 高度 / 2, 56, 粒子组, 速度=10.0, 寿命=(0.25, 1.0), 散布=2.2)
                for _ in range(16):
                    环 = [p for p in 环 if p.步进(0.05)]
                    for p in 环:
                        pc, pr = int(p.横坐标), int(p.纵坐标)
                        if 1 <= pr <= 高度 and 1 <= pc <= 宽度:
                            绘制(pr, pc, p.字符, 颜色=p.可见颜色)
                    刷新输出()
                    时间.sleep(0.032)
                时间.sleep(0.28)
            else:
                全屏清()
                重绘星空(混入辅色=样式 == "涟漪扫屏")
                画当前(
                    盲文=样式 == "涟漪扫屏" and 随机源.random() < 0.25,
                    模式="竖渐变" if 样式 == "渐变切割" else 色模式,
                )
                刷新输出()
                时间.sleep(0.68)

            if 随机源.random() < 0.85:
                for rad in range(1, min(宽度, 高度) // 3, 2):
                    for 角 in range(0, 360, 20):
                        rr = 数学.radians(角 + 拍 * 13)
                        cc = int(宽度 / 2 + 数学.cos(rr) * rad)
                        r0 = int(高度 / 2 + 数学.sin(rr) * rad * 0.5)
                        if 1 <= r0 <= 高度 and 1 <= cc <= 宽度:
                            绘制(
                                r0,
                                cc,
                                随机源.choice(_闪光字符 + _盲文低密度),
                                颜色=_淡化(随机源.choice(粒子组), 0.6),
                            )
                    刷新输出()
                    时间.sleep(0.008)

    def 绘进度条(
        行: int,
        进度值: float,
        文案: str,
        *,
        阶段键: str = "构建",
        明细: str = "",
    ) -> None:
        r"""
        三行「可核对」进度 HUD (ASCII 条体):
          1) [2/5 依赖] pip 安装 fastapi          3/6
          2) [####====····------]  42%
          3) 版本 依赖 [构建] 组装 压缩  |  已用 1:05
        数字来自真实计量 (包数/文件数/MB), 不是装饰。
        """
        清行(行)
        清行(行 + 1)
        if 行 + 2 <= 高度:
            清行(行 + 2)

        序, 键, 起, 止, 短名 = 查阶段(进度值)
        if 阶段键 in 阶段序:
            序 = 阶段序[阶段键]
            短名 = 阶段短名.get(阶段键, 短名)
            起, 止 = 阶段区间(阶段键)
            键 = 阶段键

        # 行1: 阶段 + 动作 + 明细(计量)
        主标题 = f"[{序}/{阶段总数} {短名}] {文案}"
        if 明细:
            主标题 = f"{主标题}  |  {明细}"
        绘制(
            行,
            1,
            _截断显示(主标题, 宽度 - 2),
            颜色=_线性插值(主题.辅色组[0], 主题.直升机色, 进度值),
            加粗=True,
        )

        # 行2: 分段条 — 刻度对应五阶段真实权重
        条宽 = min(42, max(20, 宽度 - 12))
        满 = max(0, min(条宽, int(round(条宽 * 进度值))))
        段起列 = max(0, min(条宽, int(条宽 * 起)))
        段止列 = max(段起列 + 1, min(条宽, int(条宽 * 止)))
        格: list[str] = []
        for i in range(条宽):
            # 阶段分界竖线 (除首尾)
            是界 = False
            for _k, sa, _sb, _n in 阶段表[1:]:
                if i == int(条宽 * sa):
                    是界 = True
                    break
            if 是界 and i != 满:
                格.append("|")
            elif i < 满:
                格.append("=" if 段起列 <= i < 段止列 else "#")
            else:
                格.append("." if 段起列 <= i < 段止列 else "-")
        百分 = f"{进度值 * 100:5.1f}%"
        条串 = f"[{''.join(格)}]{百分}"
        绘制(
            行 + 1,
            max(1, (宽度 - len(条串)) // 2),
            条串,
            颜色=_线性插值(主题.渐变甲, 主题.渐变乙, 进度值),
            加粗=True,
        )

        # 行3: 阶段名 + 已用时
        if 行 + 2 <= 高度:
            零件: list[str] = []
            for k, _a, _b, 名 in 阶段表:
                零件.append(f"[{名}]" if k == 键 else f" {名} ")
            已用 = ""
            if 状态.开始时刻 > 0:
                已用 = f" | {格式化耗时(时间.monotonic() - 状态.开始时刻)}"
            绘制(
                行 + 2,
                1,
                _截断显示("".join(零件) + 已用, 宽度 - 2),
                颜色=_淡化(主题.直升机色, 0.9),
            )

    def 巡航位姿(进度值: float, 帧: int) -> tuple[int, int, bool]:
        r"""
        进度 0→1 映射为来回巡航 (三角波), 返回 (列, 行, 朝右)。
        进度越高飞得越稳; 接近完成时略降高度准备降落。
        """
        p = max(0.0, min(1.0, 进度值))
        左边距 = 2
        右边距 = max(左边距 + 1, 宽度 - _直升机宽度 - 2)
        航宽 = 右边距 - 左边距
        # 半程: 0→1 右飞, 1→2 左飞, ...
        相位 = p * _巡航半程数
        段 = int(相位)
        段内 = 相位 - 段
        朝右 = 段 % 2 == 0
        if 朝右:
            x比例 = 段内
        else:
            x比例 = 1.0 - 段内
        列 = 左边距 + int(航宽 * x比例)

        降高 = 波幅 * (1.0 - 0.55 * p)  # 接近完成略降
        if 航线 == "正弦":
            y = 基准行 + 降高 * 数学.sin(波频 * p * 数学.tau + 帧 * 0.09)
        elif 航线 == "三角":
            phase = (p * 波频 + 帧 * 0.01) % 1.0
            tri = 1 - abs(phase * 2 - 1) * 2
            y = 基准行 + 降高 * tri
        elif 航线 == "噪声":
            y = 基准行 + 降高 * 数学.sin(p * 7.1 + 噪声相位) * 数学.cos(帧 * 0.07 + p * 3)
        elif 航线 == "螺旋":
            y = 基准行 + 降高 * 数学.sin(p * 数学.tau * 2.5 + 帧 * 0.12)
        else:
            y = 基准行 + 降高 * (1 if int(p * 8 + 帧 * 0.02) % 2 == 0 else -1) * (
                0.5 + 0.5 * 数学.sin(p * 5)
            )
        行 = max(2, min(_地面基准行() - _直升机高度 - 1, int(y)))
        return 列, 行, 朝右

    def 绘直升机(
        列: int,
        行: int,
        帧: int,
        *,
        朝右: bool = True,
        坠毁: bool = False,
        旋翼停: bool = False,
    ) -> None:
        if 坠毁:
            机色 = (255, 90, 90)
            梁色 = (160, 60, 45)
            舱色 = (255, 130, 90)
        else:
            机色 = _线性插值(
                主题.直升机色,
                主题.辅色组[帧 % len(主题.辅色组)],
                0.12 + 0.22 * abs(数学.sin(帧 * 0.12)),
            )
            梁色 = _淡化(机色, 0.5)  # 细尾梁: 更淡, 与短粗座舱对比
            舱色 = _线性插值(机色, (255, 255, 255), 0.12)

        机身 = _机身朝右 if 朝右 else _机身朝左
        # 主轮廓在行1 (行0 占位)
        轮廓行 = 机身[1] if len(机身) > 1 else 机身[0]
        舱心 = _座舱中心列(轮廓行)
        旋翼字 = _短旋翼帧[0 if 旋翼停 else (帧 % len(_短旋翼帧))]
        旋翼宽 = len(旋翼字)
        旋翼左 = 列 + 舱心 - 旋翼宽 // 2
        尾桨符 = "x" if 旋翼停 else _尾桨帧[帧 % len(_尾桨帧)]

        # 1) 主旋翼 — 仅座舱顶上一小段
        for 列索引, 字符 in enumerate(旋翼字):
            画列 = 旋翼左 + 列索引
            if 字符 != " " and 1 <= 画列 <= 宽度 and 1 <= 行 <= 高度:
                绘制(行, 画列, 字符, 颜色=机色, 加粗=True)
        # 2) 桅杆: 旋翼中心落到座舱顶
        桅杆列 = 列 + 舱心
        桅杆行 = 行 + 1
        if 1 <= 桅杆列 <= 宽度 and 1 <= 桅杆行 <= 高度:
            绘制(桅杆行, 桅杆列, "|", 颜色=机色, 加粗=True)

        # 3) 机身各层 (跳过占位行0 的空白桅杆行, 桅杆已单独画)
        for 机身行索引, 行文本 in enumerate(机身):
            if 机身行索引 == 0:
                continue
            画行 = 行 + 1 + 机身行索引
            for 列索引, 字符 in enumerate(行文本):
                画列 = 列 + 列索引
                if 字符 == " " or not (1 <= 画列 <= 宽度 and 1 <= 画行 <= 高度):
                    continue
                # 桅杆列上若轮廓也有笔画, 保留轮廓 (座舱顶)
                绘字 = 尾桨符 if 字符 == "?" else 字符
                if 字符 == "?":
                    色, 粗 = (主题.辅色组[帧 % len(主题.辅色组)] if not 坠毁 else 机色), True
                elif 字符 in _垂尾字符:
                    色, 粗 = _线性插值(机色, 主题.渐变乙, 0.3), True
                elif 字符 in _尾梁字符 or 字符 == "+":
                    # '+' 是梁与舱的衔接节
                    色, 粗 = 梁色, False
                elif 字符 in _座舱字符 or 字符 in "<>":
                    色, 粗 = 舱色, True
                elif 字符 in _起落撬字符:
                    色, 粗 = _淡化(机色, 0.7), False
                else:
                    色, 粗 = 机色, True
                绘制(画行, 画列, 绘字, 颜色=色, 加粗=粗)

        # 4) 机头灯: 落在座舱前缘
        if not 坠毁:
            if 朝右:
                头 = 轮廓行.rfind(">")
                灯列 = 列 + (头 if 头 >= 0 else 舱心 + 2)
            else:
                头 = 轮廓行.find("<")
                灯列 = 列 + (头 if 头 >= 0 else 舱心 - 2)
            灯行 = 行 + 2
            if 1 <= 灯行 <= 高度 and 1 <= 灯列 <= 宽度:
                绘制(
                    灯行,
                    灯列,
                    "*" if 帧 % 6 < 3 else "+",
                    颜色=随机源.choice(((255, 80, 80), (80, 255, 120), 主题.辅色组[0])),
                    加粗=True,
                )

    def _停机坪行() -> int:
        r"""机腹落在地面上: 机顶行 = 地面 - 机高。"""
        return max(2, _地面基准行() - _直升机高度)

    def _画停机坪(坪列: int, 坪行: int) -> None:
        r"""完整地面 + 停机坪 H 区。"""
        绘完整地面()
        地 = _地面基准行()
        for c in range(max(1, 坪列 - 1), min(宽度, 坪列 + _直升机宽度 + 1)):
            绘制(地, c, "=", 颜色=_线性插值(主题.渐变乙, 主题.直升机色, 0.4), 加粗=True)
        中 = 坪列 + _直升机宽度 // 2
        if 1 <= 中 <= 宽度:
            绘制(地, 中, "H", 颜色=主题.直升机色, 加粗=True)

    def 起飞演出() -> tuple[int, int, bool]:
        r"""
        任务开始: 停机坪热车 → 垂直爬升至巡航高度 (无飞机状态旁白)。
        返回巡航起始 (列, 行, 朝右)。
        """
        坪列 = max(2, (宽度 - _直升机宽度) // 2)
        坪行 = _停机坪行()
        巡航行 = max(2, min(_地面基准行() - _直升机高度 - 2, 基准行))
        朝右 = True
        HUD = 高度 - 3

        # 1) 地面热车
        for 步 in range(14):
            拷贝背景到帧()
            _画停机坪(坪列, 坪行)
            if 步 > 4:
                地 = _地面基准行()
                for c in range(max(1, 坪列 - 1), min(宽度, 坪列 + _直升机宽度 + 1)):
                    if 随机源.random() < 0.35:
                        绘制(地 - 1, c, 随机源.choice(".:*"), 颜色=_淡化(主题.辅色组[0], 0.55))
            绘直升机(坪列, 坪行, 步, 朝右=朝右, 旋翼停=步 < 4)
            绘进度条(HUD, 0.0, "", 阶段键="版本", 明细="")
            冲刷整帧()
            时间.sleep(0.07)

        # 2) 垂直爬升
        行 = float(坪行)
        for 步 in range(26):
            行 += (巡航行 - 行) * 0.13
            拷贝背景到帧()
            _画停机坪(坪列, 坪行)
            if 步 < 12:
                地 = _地面基准行()
                for c in range(max(1, 坪列), min(宽度, 坪列 + _直升机宽度)):
                    if 随机源.random() < 0.25:
                        绘制(地 - 1, c, ".", 颜色=_淡化(主题.星空色组[0], 0.5))
            绘直升机(坪列, int(行), 步 + 14, 朝右=朝右, 旋翼停=False)
            绘进度条(HUD, 0.0, "", 阶段键="版本", 明细="")
            冲刷整帧()
            时间.sleep(0.07)

        # 3) 定高悬停一瞬
        for 步 in range(6):
            拷贝背景到帧()
            _画停机坪(坪列, 坪行)
            绘直升机(坪列, 巡航行, 步 + 40, 朝右=朝右)
            绘进度条(HUD, 0.0, "", 阶段键="版本", 明细="")
            冲刷整帧()
            时间.sleep(0.08)
        return 坪列, 巡航行, 朝右

    def 降落演出(起始列: int, 起始行: int, 朝右: bool) -> None:
        r"""成功: 滑向停机坪并降落 (无飞机状态旁白)。"""
        坪列 = max(2, (宽度 - _直升机宽度) // 2)
        坪行 = _停机坪行()
        HUD = 高度 - 3
        列, 行 = float(起始列), float(起始行)
        for 步 in range(28):
            列 += (坪列 - 列) * 0.14
            行 += (坪行 - 行) * 0.12
            拷贝背景到帧()
            _画停机坪(坪列, 坪行)
            绘直升机(int(列), int(行), 步, 朝右=朝右, 旋翼停=步 > 22)
            绘进度条(HUD, 1.0, "", 阶段键="压缩", 明细="")
            冲刷整帧()
            时间.sleep(0.08)
        拷贝背景到帧()
        _画停机坪(坪列, 坪行)
        绘直升机(坪列, 坪行, 0, 朝右=朝右, 旋翼停=True)
        绘进度条(HUD, 1.0, "搞定了!", 阶段键="压缩", 明细="")
        冲刷整帧()
        时间.sleep(0.25)

    def 绘跑道与里程碑(进度值: float) -> None:
        r"""巡航时刷新整幅地面, 并标里程碑。"""
        绘完整地面(进度高亮=进度值)
        地 = _地面基准行()
        草 = 地 - 1
        for m in 里程碑点:
            if 进度值 * 100 >= m:
                列 = max(1, min(宽度, int(宽度 * m / 100)))
                if 草 >= 2:
                    绘制(草, 列, "v", 颜色=主题.辅色组[m % len(主题.辅色组)], 加粗=True)

    def 里程碑烟花(进度值: float) -> None:
        pct = int(进度值 * 100)
        for m in 里程碑点:
            if pct >= m and m not in 已里程碑:
                已里程碑.add(m)
                _爆发粒子(
                    粒子列表,
                    宽度 * m / 100,
                    随机源.uniform(3, 高度 * 0.45),
                    随机源.randint(22, 40),
                    混色盘(),
                    速度=8.0,
                    寿命=(0.3, 1.0),
                    散布=1.5,
                )

    def 坠机演出(起始列: int, 起始行: int, 原因: str) -> None:
        r"""失败: 起飞后的反面 — 失控下坠 + 爆炸 (整帧缓冲, 与起飞/降落一致)。"""
        坠毁色 = ((255, 200, 80), (255, 120, 60), (255, 70, 70), 主题.辅色组[0])
        当前列 = float(起始列)
        当前行 = float(起始行)
        触地行 = float(_停机坪行())
        本地: list[_粒子] = []
        for 步进 in range(22):
            当前列 += 0.6 + (0.15 if 步进 > 10 else 0)
            当前行 += 0.55 + 步进 * 0.02
            当前列 = min(float(宽度 - _直升机宽度 - 1), 当前列)
            当前行 = min(触地行, 当前行)
            拷贝背景到帧()
            绘完整地面()
            _爆发粒子(
                本地,
                当前列 + _直升机宽度 * 0.45,
                当前行 + _直升机高度 * 0.7,
                8 + 步进 // 3,
                坠毁色,
                速度=8.0,
                寿命=(0.2, 0.7),
                散布=1.4,
            )
            本地[:] = [p for p in 本地 if p.步进(0.06)]
            for p in 本地[:50]:
                pc, pr = int(p.横坐标), int(p.纵坐标)
                if 1 <= pr <= 高度 and 1 <= pc <= 宽度:
                    绘制(pr, pc, p.字符, 颜色=p.可见颜色)
            绘直升机(int(当前列), int(当前行), 步进, 坠毁=True, 旋翼停=步进 > 14)
            绘进度条(
                高度 - 3,
                max(0.0, min(1.0, 状态.目标进度)),
                "",
                阶段键=状态.阶段键,
                明细="",
            )
            冲刷整帧()
            时间.sleep(0.06)

        # 触地爆炸
        _爆发粒子(
            本地,
            当前列 + _直升机宽度 * 0.5,
            当前行 + _直升机高度 * 0.8,
            55,
            坠毁色,
            速度=11.0,
            寿命=(0.3, 1.0),
            散布=2.2,
        )
        for _ in range(12):
            拷贝背景到帧()
            本地[:] = [p for p in 本地 if p.步进(0.07)]
            for p in 本地[:50]:
                pc, pr = int(p.横坐标), int(p.纵坐标)
                if 1 <= pr <= 高度 and 1 <= pc <= 宽度:
                    绘制(pr, pc, p.字符, 颜色=p.可见颜色)
            冲刷整帧()
            时间.sleep(0.05)

        帧清()
        标题 = "X 打包失败"
        原因行 = _截断显示(f"原因: {原因}", 宽度 - 4)
        中行 = max(2, 高度 // 2 - 1)
        绘制(中行, max(1, (宽度 - len(标题)) // 2), 标题, 颜色=(255, 90, 90), 加粗=True)
        绘制(
            中行 + 1,
            max(1, (宽度 - _中日韩宽度(原因行)) // 2),
            原因行,
            颜色=(255, 200, 120),
            加粗=True,
        )
        角标 = f"[{人格}]"
        绘制(
            中行 + 2,
            max(1, (宽度 - _中日韩宽度(角标)) // 2),
            角标,
            颜色=_淡化(主题.辅色组[0], 0.8),
        )
        提示 = "按任意键退出…"  # 失败老实退出, 不恶搞
        绘制(
            min(高度, 中行 + 4),
            max(1, (宽度 - _中日韩宽度(提示)) // 2),
            提示,
            颜色=_淡化(主题.辅色组[0], 0.85),
        )
        冲刷整帧()
        _等待任意键("")

    def 结算页() -> None:
        模式 = 随机源.choice(("盲文溶出", "百叶窗", "像素雨", "螺旋", "故障恢复"))
        if 模式 == "盲文溶出":
            行顺序 = list(range(1, 高度 + 1))
            随机源.shuffle(行顺序)
            for 行 in 行顺序:
                绘制(
                    行,
                    1,
                    "".join(随机源.choice(_盲文中密度) for _ in range(宽度)),
                    颜色=_线性插值(主题.渐变甲, 主题.渐变乙, 行 / 高度),
                )
                if 行 % 2 == 0:
                    刷新输出()
                    时间.sleep(0.003)
            for 行 in 行顺序:
                清行(行)
                if 行 % 3 == 0:
                    刷新输出()
        elif 模式 == "百叶窗":
            for 列 in range(1, 宽度 + 1, 2):
                for 行 in range(1, 高度 + 1):
                    绘制(行, 列, "┃", 颜色=_线性插值(主题.渐变甲, 主题.辅色组[0], 列 / 宽度))
                刷新输出()
                时间.sleep(0.008)
            全屏清()
        elif 模式 == "像素雨":
            for _ in range(高度 * 2):
                for __ in range(宽度 // 4):
                    绘制(
                        随机源.randint(1, 高度),
                        随机源.randint(1, 宽度),
                        随机源.choice(_盲文高密度 + _闪光字符),
                        颜色=随机源.choice(混色盘()),
                    )
                刷新输出()
                时间.sleep(0.012)
            全屏清()
        elif 模式 == "螺旋":
            for r in range(0, max(宽度, 高度), 1):
                for 角 in range(0, 360, 10):
                    rad = 数学.radians(角 + r * 8)
                    cc = int(宽度 / 2 + 数学.cos(rad) * r * 0.55)
                    rr = int(高度 / 2 + 数学.sin(rad) * r * 0.35)
                    if 1 <= rr <= 高度 and 1 <= cc <= 宽度:
                        绘制(
                            rr,
                            cc,
                            随机源.choice(_盲文中密度),
                            颜色=_线性插值(主题.渐变甲, 主题.渐变乙, r / max(宽度, 1)),
                        )
                if r % 2 == 0:
                    刷新输出()
                    时间.sleep(0.006)
            全屏清()
        else:
            for _ in range(6):
                for __ in range(50):
                    绘制(
                        随机源.randint(1, 高度),
                        随机源.randint(1, 宽度),
                        随机源.choice("░▒▓█╳"),
                        颜色=随机源.choice(混色盘()),
                    )
                刷新输出()
                时间.sleep(0.04)
                全屏清()

        重绘星空(混入辅色=True, 密度=1.15)
        # 结算用高密度轮廓字, 与开场字母块区分
        结字形 = _结算标题字形
        结宽 = _结算标题宽度
        标题上 = max(2, 高度 // 2 - len(结字形) // 2 - 6)
        标题左 = max(1, (宽度 - 结宽) // 2)
        显现列 = list(range(结宽))
        随机源.shuffle(显现列)
        批 = max(1, 结宽 // 14)
        已显: set[int] = set()
        for 起 in range(0, len(显现列), 批):
            已显.update(显现列[起 : 起 + 批])
            for 序号, 行文本 in enumerate(结字形):
                行 = 标题上 + 序号
                if not (1 <= 行 <= 高度):
                    continue
                for 列索引, 字符 in enumerate(行文本):
                    if 列索引 not in 已显 or 字符 == " ":
                        continue
                    列 = 标题左 + 列索引
                    if 1 <= 列 <= 宽度:
                        绘制(
                            行,
                            列,
                            字符,
                            颜色=_线性插值(
                                主题.渐变甲,
                                主题.渐变乙,
                                列索引 / max(结宽 - 1, 1),
                            ),
                            加粗=True,
                        )
            刷新输出()
            时间.sleep(0.012)
        # 终态整幅结算标题
        for 序号, 行文本 in enumerate(结字形):
            行 = 标题上 + 序号
            if not (1 <= 行 <= 高度):
                continue
            for 列索引, 字符 in enumerate(行文本):
                if 字符 == " ":
                    continue
                列 = 标题左 + 列索引
                if 1 <= 列 <= 宽度:
                    绘制(
                        行,
                        列,
                        字符,
                        颜色=_线性插值(主题.渐变甲, 主题.渐变乙, 列索引 / max(结宽 - 1, 1)),
                        加粗=True,
                    )
        刷新输出()

        副 = 随机源.choice(
            (
                "* 搞定了! *",
                f"* 搞定了! · {人格} *",
                ">> 搞定了! <<",
            )
        )
        副行 = 标题上 + len(结字形) + 1
        if 副行 <= 高度:
            游 = max(1, (宽度 - _中日韩宽度(副)) // 2)
            for i, ch in enumerate(副):
                绘制(
                    副行,
                    游,
                    ch,
                    颜色=_线性插值(主题.辅色组[0], 主题.直升机色, i / max(len(副) - 1, 1)),
                    加粗=True,
                )
                游 += _单元宽(ch) or 1
                刷新输出()
                时间.sleep(0.018)

        with 状态.锁:
            版, 绿, 包, 大小, 耗时 = (
                状态.新版本,
                状态.绿色根,
                状态.归档,
                状态.归档大小兆,
                状态.耗时秒,
            )
        信息上 = 副行 + 2
        信息左 = max(1, (宽度 - 64) // 2)
        行表 = [
            (f"  ✦ 版本   │ v{版}", 主题.辅色组[0]),
            (f"  ✦ 绿色   │ {_截断显示(str(绿) if 绿 else '—', 宽度 - 18)}", 主题.辅色组[1 % 3]),
            (f"  ✦ 发布   │ {_截断显示(str(包) if 包 else '—', 宽度 - 18)}", 主题.辅色组[2 % 3]),
            (f"  ✦ 大小   │ {大小:.1f} MB", 主题.渐变甲),
            (f"  ✦ 耗时   │ {格式化耗时(耗时)}", 主题.直升机色),
            (f"  ✦ 演出   │ {人格} / {航线} / {背景层} / {进度皮}", _淡化(主题.直升机色, 0.9)),
            ("", (0, 0, 0)),
            ("  ✦ 双击 MyBiOut!.exe 即可使用（无控制台黑框）", 主题.渐变乙),
            ("  ✦ 仓库   │ https://github.com/Water-Run/MyBiOut", 主题.渐变甲),
        ]
        for i, (行文本, 色) in enumerate(行表):
            行 = 信息上 + i
            if 行 > 高度 or not 行文本:
                continue
            绘制(行, 信息左, _截断显示(行文本, 宽度 - 2), 颜色=色)
        冲刷整帧()
        时间.sleep(0.35)

        # 礼花: 少次数、整帧冲刷, 避免逐字刷新闪爆
        for _wave in range(3):
            烟: list[_粒子] = []
            for _ in range(3):
                _爆发粒子(
                    烟,
                    随机源.uniform(宽度 * 0.15, 宽度 * 0.85),
                    随机源.uniform(2.0, max(3.0, 标题上 - 0.5)),
                    24,
                    混色盘(),
                    速度=7.0,
                    寿命=(0.3, 0.9),
                    散布=1.0,
                )
            for _ in range(10):
                烟 = [p for p in 烟 if p.步进(0.08)]
                for p in 烟:
                    pc, pr = int(p.横坐标), int(p.纵坐标)
                    if 1 <= pr <= 高度 and 1 <= pc <= 宽度:
                        绘制(pr, pc, p.字符, 颜色=p.可见颜色)
                冲刷整帧()
                时间.sleep(0.07)
        提示 = "按任意键关机…"  # 一点点恶意: 真 · shutdown -s -t 0
        提示行 = min(高度, 信息上 + len(行表) + 1)
        绘制(
            提示行,
            max(1, (宽度 - _中日韩宽度(提示)) // 2),
            提示,
            颜色=_淡化(主题.辅色组[0], 0.9),
            加粗=True,
        )
        冲刷整帧()
        _等待任意键("")
        _真关机(
            绘制=绘制,
            冲刷=冲刷整帧,
            行=提示行,
            宽度=宽度,
            颜色=(255, 90, 90),
        )

    原始写出(_进入备用屏 + _隐藏光标 + _清屏)
    try:
        播放震撼倒计时()
        # 倒计时与代码检查结束后: 先起飞, 再开工巡航
        状态行 = 高度 - 3
        粒子上限 = 40
        背景刷新间隔 = 12
        帧间隔 = 0.11
        重建飞行背景()
        起飞演出()

        if 开工 is not None:
            线程.Thread(target=开工, daemon=True).start()
            状态.进入阶段("版本", "", 段内=0.0, 明细="")

        while True:
            目标, 文案, 阶段键, 明细, 已结束, 已成功, 失败原因 = 状态.快照()

            # 显示进度只平滑追赶真实权威进度, 不做无依据假爬
            差 = 目标 - 显示进度
            if 差 > 0:
                步进量 = min(差 * 0.12, 进度最大步进 * (2.0 if 差 > 0.05 else 1.0))
                显示进度 += 步进量
            elif 差 < 0:
                显示进度 = 目标
            if abs(目标 - 显示进度) < 0.001:
                显示进度 = 目标

            直升机列, 直升机行, 朝右 = 巡航位姿(显示进度, 帧号)

            if 帧号 % 背景刷新间隔 == 0:
                重建飞行背景()

            拷贝背景到帧()
            绘跑道与里程碑(显示进度)
            里程碑烟花(显示进度)

            粒子列表 = [p for p in 粒子列表 if p.步进(0.08)]
            for p in 粒子列表[:粒子上限]:
                pc, pr = int(p.横坐标), int(p.纵坐标)
                if 1 <= pr <= 高度 - 3 and 1 <= pc <= 宽度:
                    绘制(pr, pc, p.字符, 颜色=p.可见颜色)

            尾焰列 = float(直升机列 + (2 if 朝右 else _直升机宽度 - 3))
            尾焰行 = float(直升机行 + 3)
            尾速 = -2.8 if 朝右 else 2.8
            for i in range(2):
                存活 = 随机源.uniform(0.15, 0.45)
                色 = 随机源.choice(主题.辅色组)
                粒子列表.append(
                    _粒子(
                        横坐标=尾焰列,
                        纵坐标=尾焰行 + 随机源.uniform(-0.3, 0.3),
                        横速度=尾速,
                        纵速度=随机源.uniform(-0.4, 0.4),
                        寿命=存活,
                        最大寿命=存活,
                        颜色=色,
                    )
                )
            if len(粒子列表) > 粒子上限:
                del 粒子列表[: len(粒子列表) - 粒子上限]

            绘直升机(直升机列, 直升机行, 帧号, 朝右=朝右)
            绘进度条(状态行, 显示进度, 文案, 阶段键=阶段键, 明细=明细)
            前行, 前列 = 直升机行, 直升机列
            冲刷整帧()

            if 已结束:
                if 已成功:
                    while 显示进度 < 0.999:
                        显示进度 += min(0.02, 1.0 - 显示进度)
                        直升机列, 直升机行, 朝右 = 巡航位姿(显示进度, 帧号)
                        拷贝背景到帧()
                        绘完整地面(进度高亮=显示进度)
                        绘直升机(直升机列, 直升机行, 帧号, 朝右=朝右)
                        绘进度条(状态行, 显示进度, 文案, 阶段键="压缩", 明细=明细)
                        帧号 += 1
                        冲刷整帧()
                        时间.sleep(0.08)
                    降落演出(直升机列, 直升机行, 朝右)
                    结算页()
                    return
                坠机演出(直升机列, 直升机行, 失败原因 or "未知错误")
                return

            帧号 += 1
            时间.sleep(帧间隔)
    finally:
        原始写出(_重置样式 + _显示光标 + _退出备用屏)


# ---------- 版本 / 环境 ----------
# 中文版本号: 年(二位) + 月(二位) + 月内序号(甲…丑 共 12)
# 例: 二六〇七甲 = 2026 年 7 月 第 1 个发布包
_中文数码: str = "〇一二三四五六七八九"
_月内序标: str = "甲乙丙丁戊己庚辛壬癸子丑"  # 1..12


def _二位中文(数: int) -> str:
    数 = max(0, int(数)) % 100
    return _中文数码[数 // 10] + _中文数码[数 % 10]


def _月内序标到序号(标记: str) -> int | None:
    r"""
    仅接受单字月内序标 (甲…丑)。多字尾巴若用 ``in`` 子串匹配会误判
    (如 ``子丑 in 甲…子丑`` 为真且 index 落在子上), 故先要求恰好一字。
    """
    标记 = (标记 or "").strip()
    if len(标记) != 1:
        return None
    位置 = _月内序标.find(标记)
    return 位置 + 1 if 位置 >= 0 else None


def _序号到月内序标(序号: int) -> str:
    if not 1 <= 序号 <= len(_月内序标):
        raise ValueError(f"月内序号须为 1..{len(_月内序标)}, 收到 {序号}")
    return _月内序标[序号 - 1]


def 本月版本前缀(当日: 日期 | None = None) -> str:
    r"""如 二六〇七 (年二位 + 月二位, 中文数码)。"""
    天 = 当日 or 日期.today()
    return _二位中文(天.year % 100) + _二位中文(天.month)


def 读取当前版本() -> str:
    if 版本文件路径.is_file():
        行列表 = 版本文件路径.read_text(encoding="utf-8").splitlines()
        if 行列表 and 行列表[0].strip():
            return 行列表[0].strip()
    return "〇〇〇〇甲"


def 计算下一版本(旧版本: str, 当日: 日期 | None = None) -> str:
    r"""
    下一中文版本号 (按月递增, 每月最多 12 个)。
    兼容读取旧式 YY.MM.DD.序号: 同年同月则序标从 1 起重新计中文轨
    (旧轨按日计数, 不直接映射到甲乙, 避免误跳号)。
    本月无有效序标 / 「重来」哨兵 → 从甲起算。
    """
    天 = 当日 or 日期.today()
    前缀 = 本月版本前缀(天)
    序号 = 1
    旧 = (旧版本 or "").strip()
    if 旧.startswith(前缀):
        尾 = 旧[len(前缀) :]
        旧序 = _月内序标到序号(尾)
        if 旧序 is not None:
            序号 = 旧序 + 1
    # 旧阿拉伯格式 26.07.19.3 — 仅用于识别「已是本月产物」, 中文轨仍从甲起算
    # 若已是中文且本月已满 12 → 坠机
    if 序号 > len(_月内序标):
        失败退出(
            "受不了版本号溢出来了....\n"
            "之后的版本下个月再来编译吧~\n"
            f"  ({前缀}甲…{_月内序标[-1]} 共 {len(_月内序标)} 个已满; 当前 {旧})\n"
            f"  或先:  python 打包.py 重来  (从甲重新计时)"
        )
    return 前缀 + _序号到月内序标(序号)


def 写入版本文件(版本: str, 编译时间: str | None = None) -> None:
    r"""写入可用于版本递增的首行及本次编译时间。"""
    时间文本 = 编译时间 or 日期时间.now().strftime("%Y-%m-%d %H:%M:%S")
    版本文件路径.write_text(f"{版本}\n编译时间：{时间文本}\n", encoding="utf-8")


def 重来本月从甲(当日: 日期 | None = None) -> str:
    r"""
    版本计时归零: 写入「本月前缀」哨兵 (无序标), 使下次 计算下一版本 得到 本月甲。
    :return: 下次将产出的版本号 (…甲)
    """
    前缀 = 本月版本前缀(当日)
    下次甲 = 前缀 + _序号到月内序标(1)
    写入版本文件(前缀)
    return 下次甲


def 检查运行平台() -> None:
    if 系统.platform != "win32":
        失败退出("本打包脚本仅支持 Windows 系统。")
    if 系统.maxsize <= 2**32:
        失败退出("本打包脚本仅支持 64 位 Windows。")
    if not 程序包目录.is_dir():
        失败退出(f"未找到程序包目录: {程序包目录}")
    if not (程序包目录 / "main.py").is_file():
        失败退出(f"未找到程序入口: {程序包目录 / 'main.py'}")


# ---------- 打包步骤（可被进度驱动） ----------


def 执行命令(
    命令: list[str],
    *,
    工作目录: 路径 | None = None,
    步骤说明: str = "",
    状态: 打包进度 | None = None,
) -> None:
    显示 = " ".join(命令)
    静默 = 状态 is not None and not 状态.纯文本
    if not 静默:
        print(_着色("  > 执行: ", _当前主题().辅色组[1 % 3]) + 显示)
        if 工作目录 is not None:
            打印信息(f"工作目录: {工作目录}")
    # TUI 模式: 捕获输出后写入日志 (不用句柄重定向, 避免 Windows 句柄继承问题)
    if 静默:
        日志目录 = 工程根目录 / 产物输出目录名
        日志目录.mkdir(parents=True, exist_ok=True)
        日志文件 = 日志目录 / "pack_cmd.log"
        结果 = 子进程.run(
            命令,
            check=False,
            cwd=str(工作目录) if 工作目录 else None,
            stdin=子进程.DEVNULL,
            stdout=子进程.PIPE,
            stderr=子进程.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            with 日志文件.open("a", encoding="utf-8", errors="replace") as 日志:
                日志.write(f"\n===== {步骤说明 or '命令'} =====\n{显示}\n")
                if 结果.stdout:
                    日志.write(结果.stdout)
                    if not 结果.stdout.endswith("\n"):
                        日志.write("\n")
                if 结果.stderr:
                    日志.write(结果.stderr)
                    if not 结果.stderr.endswith("\n"):
                        日志.write("\n")
        except OSError:
            pass
    else:
        结果 = 子进程.run(命令, check=False, cwd=str(工作目录) if 工作目录 else None)
    if 结果.returncode == 0:
        return
    前缀 = f"{步骤说明}失败" if 步骤说明 else "外部命令执行失败"
    说明 = f"{前缀}（退出码 {结果.returncode}）\n  命令: {显示}"
    if 静默:
        状态.标记失败(说明.replace("\n", " | "))
        raise SystemExit(结果.returncode if 结果.returncode else 1)
    失败退出(说明, 结果.returncode if 结果.returncode else 1)


def 安装依赖(状态: 打包进度 | None = None) -> None:
    r"""按包逐个安装, 进度 = 已完成包数 / 总包数 (真实计量)。"""
    总数 = len(依赖列表)
    if 状态 is None or 状态.纯文本:
        打印步骤(1, 4, "安装依赖")
        打印信息("将安装: " + "、".join(依赖列表))
    if 状态:
        状态.进入阶段(
            "依赖",
            "检查/安装依赖",
            段内=0.0,
            明细=f"0/{总数}",
            计量当前=0,
            计量总共=总数,
        )
    for 序号, 包名 in enumerate(依赖列表):
        if 状态:
            状态.进入阶段(
                "依赖",
                f"pip install {包名}",
                段内=(序号 + 0.35) / 总数,
                明细=f"{序号}/{总数} -> {包名}",
                计量当前=序号,
                计量总共=总数,
            )
        pip参数 = [
            系统.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            包名,
        ]
        if 状态 is not None and not 状态.纯文本:
            pip参数.insert(4, "-q")
        执行命令(pip参数, 步骤说明=f"依赖 {包名}", 状态=状态)
        if 状态:
            状态.进入阶段(
                "依赖",
                f"已就绪 {包名}",
                段内=(序号 + 1) / 总数,
                明细=f"{序号 + 1}/{总数}",
                计量当前=序号 + 1,
                计量总共=总数,
            )
        if 状态 is None or 状态.纯文本:
            打印成功(f"依赖 {序号 + 1}/{总数}: {包名}")
    if 状态:
        状态.完成阶段("依赖", "依赖全部就绪", 明细=f"{总数}/{总数}")
    if 状态 is None or 状态.纯文本:
        打印成功("依赖已就绪")


def 执行构建(状态: 打包进度 | None = None) -> None:
    global _实际产物目录
    if 状态 is None or 状态.纯文本:
        打印步骤(2, 4, "PyInstaller 构建（目录版 / 无控制台窗口）")
    清理成功, 清理消息 = 预清理构建产物目录(状态)
    if not 清理成功:
        if 状态 is None or 状态.纯文本:
            打印警告(清理消息 + " | 将使用临时目录构建")
    for 源路径, _目标 in 内嵌数据项:
        if not 源路径.exists():
            说明 = f"构建所需资源不存在: {源路径}"
            if 状态 and not 状态.纯文本:
                状态.标记失败(说明)
            失败退出(说明)

    图标文件 = 程序包目录 / "assets" / "logo.ico"
    _实际产物目录 = 工程根目录 / 产物输出目录名 / 产物显示名
    if not 清理成功:
        import uuid as _避让ID
        _临时产出根 = 工程根目录 / 产物输出目录名 / f"_tmp_{_避让ID.uuid4().hex[:6]}"
        _临时产出根.mkdir(parents=True, exist_ok=True)
        _实际产物目录 = _临时产出根 / 产物显示名
        if 状态 is None or 状态.纯文本:
            打印信息(f"dist/{产物显示名} 被占用, 产物输出到: {_临时产出根}")
    参数: list[str] = [
        系统.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        # 不用 --clean: 复用 build 缓存, 二次打包显著更快
        "--windowed",
        "--onedir",
        "--name",
        产物显示名,
        "--paths",
        str(工程根目录),
        "--distpath",
        str(_实际产物目录.parent),
        "--workpath",
        str(工程根目录 / 构建缓存目录名),
        "--specpath",
        str(工程根目录 / 构建缓存目录名),
    ]
    if 图标文件.is_file():
        参数 += ["--icon", str(图标文件)]
    for 源路径, 目标标记 in 内嵌数据项:
        参数 += ["--add-data", f"{源路径};{目标标记}"]
    for 模块名 in 隐藏导入列表:
        参数 += ["--hidden-import", 模块名]
    # webview 需要少量数据文件, 比 collect-all 轻得多
    参数 += ["--collect-data", "webview"]
    参数.append(str(程序包目录 / "main.py"))

    if 状态 is None or 状态.纯文本:
        打印信息("不嵌入本机 config.ini（避免凭证进入发布包）")
        打印信息("产物为 GUI 子系统（--windowed），双击无黑框")
        if 图标文件.is_file():
            打印信息(f"exe 图标: {图标文件.name}（assets/logo）")
        else:
            打印警告(f"未找到 {图标文件.name}，将使用默认图标")
        打印信息("增量构建: 无 --clean / 无 --collect-all")
    else:
        参数 += ["--log-level", "ERROR"]

    构建目录 = 工程根目录 / 构建缓存目录名
    产物目录 = _实际产物目录
    停止监视 = 线程.Event()

    def _监视构建体积() -> None:
        r"""用 build/dist 实际体积推进构建进度 (有物理意义的代理指标)。"""
        # 经验饱和体积: 超过后进度贴近段末但不提前标完成
        饱和字节 = 280 * 1024 * 1024
        while not 停止监视.is_set():
            体积 = 目录体积字节(构建目录) + 目录体积字节(产物目录)
            # 0.05~0.92 映射到体积, 完成仍由主线程收口
            段内 = 0.05 + 0.87 * min(1.0, 体积 / 饱和字节)
            有exe = (产物目录 / f"{产物显示名}.exe").is_file()
            文案 = "PyInstaller 分析/链接中…"
            if 体积 > 8 * 1024 * 1024:
                文案 = "PyInstaller 写出产物…"
            if 有exe:
                段内 = max(段内, 0.9)
                文案 = "产物 exe 已生成, 收尾中…"
            if 状态:
                状态.进入阶段(
                    "构建",
                    文案,
                    段内=段内,
                    明细=f"{体积 / (1024 * 1024):.0f} MB",
                )
            停止监视.wait(0.8)

    if 状态:
        状态.进入阶段("构建", "启动 PyInstaller…", 段内=0.02, 明细="0 MB")
    监视线程: 线程.Thread | None = None
    if 状态 is not None:
        监视线程 = 线程.Thread(target=_监视构建体积, daemon=True)
        监视线程.start()
    try:
        执行命令(参数, 工作目录=工程根目录, 步骤说明="PyInstaller 构建", 状态=状态)
    finally:
        停止监视.set()
        if 监视线程 is not None:
            监视线程.join(timeout=2.0)
    if 状态:
        体积 = 目录体积字节(产物目录)
        状态.完成阶段(
            "构建",
            "构建完成",
            明细=f"产物 {体积 / (1024 * 1024):.0f} MB",
        )
    if 状态 is None or 状态.纯文本:
        打印成功("可执行目录构建完成")


def 写入脱敏默认配置(目标文件: 路径, 状态: 打包进度 | None = None) -> None:
    默认分区: dict[str, dict[str, str]] | None = None
    try:
        if str(工程根目录) not in 系统.path:
            系统.path.insert(0, str(工程根目录))
        from mybiout.pages.utils import 默认设置 as 程序默认设置

        默认分区 = {分区: dict(键值) for 分区, 键值 in 程序默认设置.items()}
        if 状态 is None or 状态.纯文本:
            打印信息("默认配置模板: 已从程序包 mybiout.pages.utils 读取")
    except Exception as 异常:  # noqa: BLE001
        if 状态 is None or 状态.纯文本:
            打印警告(f"无法导入程序默认设置，改用脚本内嵌模板（{异常}）")
        默认分区 = {
            "export": {"path": r"C:\MyBiOut!", "sessdata": ""},
            "api": {
                "enabled": "false",
                "key": "",
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com/v1",
                "timeout": "infinite",
            },
            "localout": {
                "folder": "localout!",
                "bilibili_pc_cache_path": "",
                "bilibili_pc_cache_optional_when_installed": "true",
                "name_parts": "title",
                "incomplete_title_action": "partial_or_folder",
                "ffmpeg_concurrent": "3",
                "crawler_fallback": "disabled",
            },
            "bbdown": {
                "folder": "bbdown!",
                "cookie": "",
                "encoding_priority": "",
                "quality_priority": "",
                "download_danmaku": "false",
                "skip_subtitle": "false",
                "skip_cover": "false",
                "file_pattern": "<videoTitle>",
                "multi_file_pattern": "<videoTitle>/[P<pageNumberWithZero>]<pageTitle>",
                "use_aria2c": "false",
            },
            "mdout": {
                "folder": "mdout!",
                "sessdata": "",
                "include_cover": "true",
                "include_tags": "true",
                "include_stats": "true",
                "favorite_detail": "basic",
                "request_delay": "0.5",
            },
        }

    assert 默认分区 is not None
    # 无论模板来自程序包还是内嵌, 一律强制脱敏（防本机路径/凭证泄漏）
    默认分区 = 强制脱敏配置分区(默认分区)

    配置 = 配置解析器.ConfigParser(interpolation=None)
    for 分区, 键值表 in 默认分区.items():
        配置[分区] = dict(键值表)

    目标文件.parent.mkdir(parents=True, exist_ok=True)
    with 目标文件.open("w", encoding="utf-8", newline="\n") as 文件:
        文件.write("# MyBiOut! 配置文件（发布包默认；无凭证、无本机路径）\n\n")
        配置.write(文件)
    if 状态 is None or 状态.纯文本:
        打印成功(f"已写入脱敏默认配置: {目标文件.name}")


def 目录内是否有FFmpeg(工具目录: 路径) -> bool:
    for 候选 in (
        工具目录 / "ffmpeg.exe",
        工具目录 / "ffmpeg",
        工具目录 / "ffmpeg" / "ffmpeg.exe",
        工具目录 / "ffmpeg" / "bin" / "ffmpeg.exe",
        工具目录 / "BBDown" / "ffmpeg.exe",
        工具目录 / "BBDown" / "ffmpeg",
    ):
        if 候选.is_file():
            return True
    return False


def 目录内是否有ADB(工具目录: 路径) -> bool:
    for 候选 in (
        工具目录 / "adb.exe",
        工具目录 / "platform-tools" / "adb.exe",
        工具目录 / "adb" / "adb.exe",
    ):
        if 候选.is_file():
            return True
    return False


def _解析真实可执行文件(which路径: str | 路径) -> 路径 | None:
    r"""
    which 可能指向 scoop shim（小跳转壳），优先解析同目录真实 exe 或跟随 target。
    """
    源 = 路径(which路径)
    if not 源.is_file():
        return None
    # scoop shim 通常很小；真实 adb/ffmpeg 体积大得多
    try:
        if 源.stat().st_size < 500_000:
            旁路候选 = [
                源.parent / 源.name,
            ]
            # scoop apps: .../shims/adb.exe → .../apps/adb/*/platform-tools/adb.exe
            apps = 源.parent.parent / "apps"
            if apps.is_dir():
                for 子 in apps.rglob(源.name):
                    if 子.is_file() and 子.stat().st_size >= 500_000:
                        return 子
            for 候选 in 旁路候选:
                if 候选.is_file() and 候选.stat().st_size >= 500_000:
                    return 候选
    except OSError:
        pass
    return 源


def 尝试从系统路径补齐FFmpeg(工具目录: 路径, 状态: 打包进度 | None = None) -> None:
    if 目录内是否有FFmpeg(工具目录):
        if 状态 is None or 状态.纯文本:
            打印信息("已检测到旁路 ffmpeg")
        return
    系统中的 = 文件工具.which("ffmpeg")
    if not 系统中的:
        if 状态 is None or 状态.纯文本:
            打印警告("旁路与系统 PATH 均未发现 ffmpeg，稍后将按硬性条件校验")
        return
    源文件 = _解析真实可执行文件(系统中的)
    if 源文件 is None or not 源文件.is_file():
        return
    工具目录.mkdir(parents=True, exist_ok=True)
    目标文件 = 工具目录 / "ffmpeg.exe"
    文件工具.copy2(源文件, 目标文件)
    if 状态 is None or 状态.纯文本:
        打印成功(f"已从系统 PATH 复制 ffmpeg 到绿色包: {目标文件.name} ({源文件})")


def 尝试从系统路径补齐ADB(工具目录: 路径, 状态: 打包进度 | None = None) -> None:
    r"""
    将 adb.exe 及 Win 配套 dll 打进 bin/（仅 Win11 x64 目标）。
    """
    if 目录内是否有ADB(工具目录):
        if 状态 is None or 状态.纯文本:
            打印信息("已检测到旁路 adb")
        return
    系统中的 = 文件工具.which("adb.exe") or 文件工具.which("adb")
    if not 系统中的:
        if 状态 is None or 状态.纯文本:
            打印警告("旁路与系统 PATH 均未发现 adb，稍后将按硬性条件校验")
        return
    源文件 = _解析真实可执行文件(系统中的)
    if 源文件 is None or not 源文件.is_file():
        return
    工具目录.mkdir(parents=True, exist_ok=True)
    文件工具.copy2(源文件, 工具目录 / "adb.exe")
    # 同目录配套库（缺了 adb 可能启动失败）
    for 名 in ("AdbWinApi.dll", "AdbWinUsbApi.dll", "libwinpthread-1.dll"):
        旁 = 源文件.parent / 名
        if 旁.is_file():
            文件工具.copy2(旁, 工具目录 / 名)
    if 状态 is None or 状态.纯文本:
        打印成功(f"已从系统 PATH 复制 adb 到绿色包: adb.exe ({源文件})")


def 校验绿色包结构(绿色根: 路径, 状态: 打包进度 | None = None) -> None:
    r"""
    确认绿色包具备冻结运行所需文件 (无系统 Python 也能起)。
    特别防止误把 build/ 中间产物当可分发目录。
    """
    # (路径, 说明, 最小字节) — 文本可很短; DLL/exe 须够大
    必备: list[tuple[路径, str, int]] = [
        (绿色根 / f"{产物显示名}.exe", "主程序 exe", 1024 * 100),
        (绿色根 / "_internal" / "python314.dll", "内嵌 Python 运行时", 1024 * 100),
        (绿色根 / "_internal" / "python3.dll", "Python3 DLL", 1024 * 40),
        (绿色根 / "_internal" / "VCRUNTIME140.dll", "VC 运行库", 1024 * 40),
        (绿色根 / "version.txt", "版本文件", 2),
        (绿色根 / "config.ini", "默认配置", 8),
        (
            绿色根 / f"{产物显示名}.exe.config",
            ".NET Internet 区域程序集加载配置",
            64,
        ),
    ]
    for 路径点, 说明, 最小 in 必备:
        if not 路径点.is_file() or 路径点.stat().st_size < 最小:
            文 = f"绿色包结构不完整: 缺少有效 {说明} ({路径点})"
            if 状态 and not 状态.纯文本:
                状态.标记失败(文)
            失败退出(文)
    # 中间产物 build/<名>/MyBiOut!.exe 没有完整 _internal, 绝不能当绿包
    if not (绿色根 / "_internal").is_dir():
        文 = f"绿色包缺少 _internal 目录: {绿色根}"
        if 状态 and not 状态.纯文本:
            状态.标记失败(文)
        失败退出(文)
    if 状态 is None or 状态.纯文本:
        打印成功("绿色包结构校验通过 (exe + _internal/python314.dll …)")


def _终止进程树(进程: 子进程.Popen) -> None:
    r"""结束冒烟进程及其子进程 (内嵌 WebView 可能拉起子进程)。"""
    if 进程.poll() is not None:
        return
    if 系统.platform == "win32":
        with 忽略异常(Exception):
            子进程.run(
                ["taskkill", "/PID", str(进程.pid), "/T", "/F"],
                stdin=子进程.DEVNULL,
                stdout=子进程.DEVNULL,
                stderr=子进程.DEVNULL,
                check=False,
            )
        with 忽略异常(Exception):
            进程.wait(timeout=5)
        return
    with 忽略异常(Exception):
        进程.terminate()
    try:
        进程.wait(timeout=4)
    except Exception:
        with 忽略异常(Exception):
            进程.kill()


def 冒烟启动绿色包(
    绿色根: 路径,
    状态: 打包进度 | None = None,
    *,
    模拟Internet区域: bool = False,
) -> None:
    r"""
    冒烟: 以「默认内嵌窗口」模式启动冻结 exe (不用 --browser),
    同时等待 /api/version 与 WebView loaded 事件，确认后端和真实内嵌窗口均可用。
    可给 Python.Runtime.dll 写入 ZoneId=3，复现浏览器下载后解压的安全区域标记。
    捕获 uvicorn isatty / 缺 DLL / 误走浏览器 等启动问题。
    """
    可执行 = 绿色根 / f"{产物显示名}.exe"
    if not 可执行.is_file():
        文 = f"冒烟失败: 找不到 {可执行}"
        if 状态 and not 状态.纯文本:
            状态.标记失败(文)
        失败退出(文)

    # 选空闲端口
    with 套接字.socket(套接字.AF_INET, 套接字.SOCK_STREAM) as 探测:
        探测.bind(("127.0.0.1", 0))
        端口 = int(探测.getsockname()[1])

    模拟标记流: 路径 | None = None
    if 模拟Internet区域 and 操作系统.name == "nt":
        CLR组件 = 绿色根 / "_internal" / "pythonnet" / "runtime" / "Python.Runtime.dll"
        if not CLR组件.is_file():
            文 = f"下载场景冒烟失败: 找不到 CLR 组件 ({CLR组件})"
            if 状态 and not 状态.纯文本:
                状态.标记失败(文)
            失败退出(文)
        模拟标记流 = 路径(f"{CLR组件}:Zone.Identifier")
        try:
            模拟标记流.write_text("[ZoneTransfer]\nZoneId=3\n", encoding="ascii")
        except OSError as 异常:
            文 = f"下载场景冒烟失败: 无法写入 Internet 区域标记 ({异常})"
            if 状态 and not 状态.纯文本:
                状态.标记失败(文)
            失败退出(文)

    场景 = "下载后 Internet 区域" if 模拟标记流 is not None else "本地"
    if 状态 is None or 状态.纯文本:
        打印信息(f"冒烟启动绿色包 ({场景} / 内嵌窗口): 端口 {端口} …")
    elif 状态:
        状态.进入阶段("组装", "冒烟启动(内嵌窗)…", 段内=0.96, 明细=f":{端口}")

    错误日志 = 绿色根 / "startup_error.log"
    窗口状态文件 = 绿色根 / ".mybiout_window_smoke.status"
    with 忽略异常(OSError):
        if 错误日志.is_file():
            错误日志.unlink()
    with 忽略异常(OSError):
        if 窗口状态文件.is_file():
            窗口状态文件.unlink()

    进程: 子进程.Popen | None = None
    try:
        # 故意不传 --browser: 绿色包默认应走 pywebview 内嵌窗, 而非系统浏览器
        冒烟环境 = 操作系统.environ.copy()
        冒烟环境[_窗口冒烟状态环境键] = str(窗口状态文件.resolve())
        进程 = 子进程.Popen(
            [
                str(可执行),
                "--no-animation",
                "--port",
                str(端口),
            ],
            cwd=str(绿色根),
            stdin=子进程.DEVNULL,
            stdout=子进程.DEVNULL,
            stderr=子进程.DEVNULL,
            env=冒烟环境,
        )
        截止 = 时间.monotonic() + 35.0
        最后错 = ""
        后端响应 = ""
        while 时间.monotonic() < 截止:
            窗口状态 = ""
            if 窗口状态文件.is_file():
                with 忽略异常(OSError):
                    窗口状态 = 窗口状态文件.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
            if 窗口状态.startswith("error"):
                详情 = 窗口状态.partition("\n")[2].strip() or "未知窗口初始化错误"
                文 = f"冒烟失败: 内嵌窗口初始化失败。\n  {详情}"
                if 状态 and not 状态.纯文本:
                    状态.标记失败(文.replace("\n", " "))
                失败退出(文)
            if 进程.poll() is not None:
                详情 = ""
                if 错误日志.is_file():
                    with 忽略异常(OSError):
                        详情 = 错误日志.read_text(encoding="utf-8", errors="replace")[:800]
                文 = (
                    f"冒烟失败: 绿色包进程提前退出 (code={进程.returncode})。\n"
                    f"  默认模式为内嵌窗口 (无 --browser)。\n"
                    f"  常见原因: windowed 下 stdout 为 None / _internal DLL 缺失 / "
                    f"WebView2 或 pywebview 初始化失败。\n"
                    f"  {详情 or '(无 startup_error.log)'}"
                )
                if 状态 and not 状态.纯文本:
                    状态.标记失败(文.replace("\n", " "))
                失败退出(文)
            try:
                import urllib.request as 网络请求库

                with 网络请求库.urlopen(
                    f"http://127.0.0.1:{端口}/api/version",
                    timeout=1.5,
                ) as 响应:
                    体 = 响应.read().decode("utf-8", errors="replace")
                if "version" in 体:
                    后端响应 = 体.strip()[:80]
            except Exception as 异常:  # noqa: BLE001
                最后错 = str(异常)
            if 后端响应 and 窗口状态.startswith("loaded"):
                if 状态 is None or 状态.纯文本:
                    打印成功(
                        "冒烟通过(真实内嵌窗口 + 后端): "
                        f"WebView loaded; /api/version → {后端响应}"
                    )
                return
            时间.sleep(0.45)

        缺失项: list[str] = []
        if not 后端响应:
            缺失项.append(f"/api/version 未响应 ({最后错 or '超时'})")
        if not 窗口状态文件.is_file():
            缺失项.append("未收到 WebView loaded 事件")
        文 = f"冒烟失败: 约 35s 内未就绪 ({'; '.join(缺失项) or '未知状态'})"
        if 状态 and not 状态.纯文本:
            状态.标记失败(文)
        失败退出(文)
    finally:
        if 进程 is not None:
            _终止进程树(进程)
        with 忽略异常(OSError):
            窗口状态文件.unlink()
        if 模拟标记流 is not None:
            with 忽略异常(OSError):
                模拟标记流.unlink()


def 校验绿色包工具(绿色根: 路径, 状态: 打包进度 | None = None) -> None:
    工具目录 = 绿色根 / "bin"
    if not 工具目录.is_dir():
        说明 = f"组装失败：缺少工具目录 bin（{工具目录}）"
        if 状态 and not 状态.纯文本:
            状态.标记失败(说明)
        失败退出(说明)
    bbdown = 工具目录 / "BBDown.exe"
    if not bbdown.is_file():
        说明 = f"组装失败：缺少 BBDown.exe，请放到 {程序包目录 / 'bin'}"
        if 状态 and not 状态.纯文本:
            状态.标记失败(说明)
        失败退出(说明)
    尝试从系统路径补齐FFmpeg(工具目录, 状态)
    if not 目录内是否有FFmpeg(工具目录):
        说明 = "组装失败：绿色包中无 ffmpeg，且 PATH 中也没有（Win11 x64 请准备 ffmpeg.exe）"
        if 状态 and not 状态.纯文本:
            状态.标记失败(说明)
        失败退出(说明)
    尝试从系统路径补齐ADB(工具目录, 状态)
    if not 目录内是否有ADB(工具目录):
        说明 = "组装失败：绿色包中无 adb，且 PATH 中也没有（Win11 x64 请准备 platform-tools/adb.exe）"
        if 状态 and not 状态.纯文本:
            状态.标记失败(说明)
        失败退出(说明)
    if 状态 is None or 状态.纯文本:
        打印成功("旁路工具校验通过（BBDown、ffmpeg、adb）")


def 组装绿色目录(版本: str, 状态: 打包进度 | None = None) -> 路径:
    r"""按文件计数拷贝, 进度 = 已拷文件 / 总文件。"""
    if 状态 is None or 状态.纯文本:
        打印步骤(3, 4, "组装绿色运行目录")
    构建输出 = _实际产物目录 if _实际产物目录 is not None else (工程根目录 / 产物输出目录名 / 产物显示名)
    绿色根 = 工程根目录 / 产物输出目录名 / 绿色目录名
    if not 构建输出.is_dir():
        说明 = f"未找到 PyInstaller 构建输出: {构建输出}"
        if 状态 and not 状态.纯文本:
            状态.标记失败(说明)
        失败退出(说明)

    源文件列表 = 列举待拷文件(构建输出)
    源工具目录 = 程序包目录 / "bin"
    if 源工具目录.is_dir():
        源文件列表 = 源文件列表 + 列举待拷文件(源工具目录)
    总数 = max(1, len(源文件列表))
    if 状态:
        状态.进入阶段(
            "组装",
            "组装绿色目录",
            段内=0.0,
            明细=f"0/{总数} 文件",
            计量当前=0,
            计量总共=总数,
        )

    # 先组装到临时目录, 成功后再替换旧绿包, 避免半成品绿包可被误分发
    暂存根 = 路径(str(绿色根) + ".staging")
    安全移除树(暂存根, 说明="清理上次未完成的暂存绿包")
    暂存根.mkdir(parents=True, exist_ok=True)

    已拷 = 0

    def _拷一批(源根: 路径, 目标根: 路径, 文件们: list[路径]) -> None:
        nonlocal 已拷
        for 源文件 in 文件们:
            相对 = 源文件.relative_to(源根)
            目标 = 目标根 / 相对
            目标.parent.mkdir(parents=True, exist_ok=True)
            try:
                文件工具.copy2(源文件, 目标)
            except OSError as 异常:
                说明 = f"拷贝失败: {源文件} → {目标}\n  原因: {异常}"
                if 状态 and not 状态.纯文本:
                    状态.标记失败(说明.replace("\n", " "))
                失败退出(说明)
            已拷 += 1
            if 状态 and (已拷 % 25 == 0 or 已拷 == 总数):
                状态.进入阶段(
                    "组装",
                    "拷贝文件",
                    段内=min(0.95, 已拷 / 总数),
                    明细=f"{已拷}/{总数} 文件",
                    计量当前=已拷,
                    计量总共=总数,
                )

    try:
        _拷一批(构建输出, 暂存根, 列举待拷文件(构建输出))
        if 源工具目录.is_dir():
            目标工具 = 暂存根 / "bin"
            if 目标工具.exists():
                安全移除树(目标工具, 说明="覆盖 bin")
            目标工具.mkdir(parents=True, exist_ok=True)
            _拷一批(源工具目录, 目标工具, 列举待拷文件(源工具目录))
            if 状态 is None or 状态.纯文本:
                打印成功("已复制旁路工具目录 bin/")
        elif 状态 is None or 状态.纯文本:
            打印警告(f"源工具目录不存在: {源工具目录}")

        if not 版本文件路径.is_file():
            说明 = f"版本文件不存在: {版本文件路径}"
            if 状态 and not 状态.纯文本:
                状态.标记失败(说明)
            失败退出(说明)
        文件工具.copy2(版本文件路径, 暂存根 / "version.txt")
        写入脱敏默认配置(暂存根 / "config.ini", 状态)
        (暂存根 / f"{产物显示名}.exe.config").write_text(
            _CLR远程加载配置,
            encoding="utf-8",
        )
        校验绿色包工具(暂存根, 状态)
        校验绿色包结构(暂存根, 状态)
    except SystemExit:
        安全移除树(暂存根, 说明="组装失败, 丢弃暂存")
        raise
    except Exception:
        安全移除树(暂存根, 说明="组装失败, 丢弃暂存")
        raise

    # 原子替换: 删旧 → 暂存改名
    安全移除树(绿色根, 说明="替换旧绿色目录（若失败请先关闭正在运行的绿色版）")
    try:
        暂存根.rename(绿色根)
    except OSError as 异常:
        # rename 跨盘/占用失败时回退 copytree
        try:
            文件工具.copytree(暂存根, 绿色根)
            安全移除树(暂存根)
        except OSError as 异常2:
            说明 = f"无法落盘绿色目录: {异常}; 回退亦失败: {异常2}"
            if 状态 and not 状态.纯文本:
                状态.标记失败(说明)
            失败退出(说明)

    # 落盘后再冒烟 (需真实路径与完整 _internal)
    冒烟启动绿色包(绿色根, 状态, 模拟Internet区域=True)

    使用说明 = f"""MyBiOut! 绿色版  v{版本}

【启动】
1. 双击「MyBiOut!.exe」→ 内嵌窗口启动（不是浏览器）；关闭窗口即退出。
2. 只需本绿色目录 (含 _internal/ 与 bin/)，无需安装 Python。
3. 运行环境：Windows 11 的 64 位系统（亦兼容 Win10 x64，但仅保证 Win11）。
4. 内嵌窗口依赖「WebView2 运行时」。Windows 11 一般已自带；
   若窗口打不开，请安装 WebView2 Runtime 后重试（默认不会自动改开浏览器）。
5. 请勿运行工程 build/ 目录下的中间产物 exe（缺少完整 _internal，会报 Python DLL 错误）。
6. 请保留 MyBiOut!.exe.config；它用于兼容浏览器下载文件的 Internet 区域标记。

【目录说明】
· config.ini     配置文件（本发布包为默认空凭证、无本机路径，可按需填写）
· MyBiOut!.exe.config  下载包内嵌窗口运行兼容配置，请勿删除
· bin/           随包分发工具：BBDown.exe、ffmpeg.exe、adb.exe（及 ADB 配套 dll）
· _internal/     内嵌运行时 (python314.dll 等)，请整夹拷贝，勿单独挪 exe
· version.txt    版本号（界面底部会读取）
· 使用说明.txt   本文件

【可选命令行】
· 指定端口:     MyBiOut!.exe --port 23333
· 浏览器调试:   MyBiOut!.exe --browser   （仅调试用；正常请双击用内嵌窗）

【项目主页】
https://github.com/Water-Run/MyBiOut
"""
    (绿色根 / "使用说明.txt").write_text(使用说明, encoding="utf-8-sig")
    if 状态:
        状态.完成阶段("组装", "绿色目录已组装", 明细=f"{已拷}/{总数} 文件")
    if 状态 is None or 状态.纯文本:
        打印成功("已写入使用说明.txt")
        打印信息(f"绿色目录: {绿色根} ({已拷} 文件)")
    return 绿色根


# 打包时若环境无 rar, 自动落到工程 tools/ 下 (gitignore, 不进仓库)
_工具目录: 路径 = 工程根目录 / "tools"
_便携Rar目录: 路径 = _工具目录 / "rar"
# 官方 WinRAR x64 安装包 (含可创建档案的 Rar.exe; 静默装到 tools/rar)
_RAR安装包名: str = "winrar-x64-711.exe"
_RAR下载地址表: tuple[str, ...] = (
    "https://www.win-rar.com/fileadmin/winrar-versions/winrar/winrar-x64-711.exe",
    "https://www.rarlab.com/rar/winrar-x64-711.exe",
)


def _枚举Rar候选() -> list[路径]:
    候选: list[路径] = []
    for 名 in ("rar", "Rar", "RAR", "rar.exe", "Rar.exe"):
        which = 文件工具.which(名)
        if which:
            候选.append(路径(which))
    相对尾巴: tuple[tuple[str, ...], ...] = (
        ("WinRAR", "Rar.exe"),
        ("WinRAR", "rar.exe"),
        ("Programs", "WinRAR", "Rar.exe"),
    )
    for 环境键 in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "ProgramW6432"):
        根 = 操作系统.environ.get(环境键)
        if not 根:
            continue
        根路径 = 路径(根)
        for 段 in 相对尾巴:
            候选.append(根路径.joinpath(*段))
    候选.extend(
        [
            _便携Rar目录 / "Rar.exe",
            _便携Rar目录 / "rar.exe",
            工程根目录 / "tools" / "rar.exe",
            工程根目录 / "bin" / "rar.exe",
        ]
    )
    已见: set[str] = set()
    出: list[路径] = []
    for 路径点 in 候选:
        名小 = 路径点.name.lower()
        # unrar 只能解压, 不能 a 创建
        if "unrar" in 名小:
            continue
        try:
            键 = str(路径点.resolve()).lower()
        except OSError:
            键 = str(路径点).lower()
        if 键 in 已见:
            continue
        已见.add(键)
        if 路径点.is_file():
            出.append(路径点)
    return 出


def _探测Rar可执行文件() -> 路径 | None:
    列表 = _枚举Rar候选()
    return 列表[0] if 列表 else None


def _校验Rar能创建(rar程序: 路径) -> bool:
    r"""在临时目录试压一个极小 rar, 确认不是仅解压的 unrar。"""
    import tempfile as 临时库

    try:
        with 临时库.TemporaryDirectory(prefix="mybiout_rar_") as 临时:
            根 = 路径(临时)
            (根 / "t.txt").write_text("ok", encoding="utf-8")
            出 = 根 / "t.rar"
            参数 = [
                str(rar程序),
                "a",
                "-ep1",
                "-idq",
                "-m1",
                str(出),
                "t.txt",
            ]
            结果 = 子进程.run(
                参数,
                cwd=str(根),
                check=False,
                stdin=子进程.DEVNULL,
                stdout=子进程.PIPE,
                stderr=子进程.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                **(
                    {"creationflags": 0x08000000}
                    if 操作系统.name == "nt"
                    else {}
                ),
            )
            if 结果.returncode != 0 or not 出.is_file():
                # 再试不带 -idq (有的实现不认)
                参数2 = [str(rar程序), "a", "-m1", str(出), "t.txt"]
                结果2 = 子进程.run(
                    参数2,
                    cwd=str(根),
                    check=False,
                    stdin=子进程.DEVNULL,
                    stdout=子进程.PIPE,
                    stderr=子进程.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **(
                        {"creationflags": 0x08000000}
                        if 操作系统.name == "nt"
                        else {}
                    ),
                )
                if 结果2.returncode != 0 or not 出.is_file() or 出.stat().st_size < 8:
                    return False
            头 = 出.read_bytes()[:4]
            return 头 == b"Rar!"
    except OSError:
        return False


def _通过Winget补Rar() -> bool:
    winget = 文件工具.which("winget")
    if not winget:
        return False
    打印信息("尝试用 winget 安装 RAR 工具 (RARLab.WinRAR)…")
    结果 = 子进程.run(
        [
            winget,
            "install",
            "-e",
            "--id",
            "RARLab.WinRAR",
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--disable-interactivity",
        ],
        check=False,
        stdin=子进程.DEVNULL,
        stdout=子进程.PIPE,
        stderr=子进程.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return 结果.returncode == 0


def _下载文件(地址: str, 目标: 路径) -> None:
    import urllib.request as 网络请求库  # 标准库, 无额外依赖

    目标.parent.mkdir(parents=True, exist_ok=True)
    临时 = 目标.with_suffix(目标.suffix + ".download")
    if 临时.exists():
        try:
            临时.unlink()
        except OSError:
            pass
    请求 = 网络请求库.Request(
        地址,
        headers={"User-Agent": "MyBiOut-Packager/1.0 (Windows; rar-bootstrap)"},
    )
    with 网络请求库.urlopen(请求, timeout=120) as 响应, 临时.open("wb") as 写出:
        while True:
            块 = 响应.read(256 * 1024)
            if not 块:
                break
            写出.write(块)
    临时.replace(目标)


def _查找7z解压器() -> 路径 | None:
    for 名 in ("7z", "7za", "7zr", "7z.exe", "7za.exe", "7zr.exe"):
        which = 文件工具.which(名)
        if which:
            return 路径(which)
    for 环境键 in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        根 = 操作系统.environ.get(环境键)
        if not 根:
            continue
        for 相对 in (
            ("7-Zip", "7z.exe"),
            ("7-Zip", "7za.exe"),
            ("Programs", "7-Zip", "7z.exe"),
        ):
            候选 = 路径(根).joinpath(*相对)
            if 候选.is_file():
                return 候选
    便携 = _工具目录 / "7zr.exe"
    if 便携.is_file():
        return 便携
    return None


def _确保7z解压器() -> 路径 | None:
    r"""优先系统 7-Zip; 否则下载官方 7zr.exe (公有领域/LGPL, 仅用于抽出安装包)。"""
    已有 = _查找7z解压器()
    if 已有 is not None:
        return 已有
    目标 = _工具目录 / "7zr.exe"
    地址表 = (
        "https://www.7-zip.org/a/7zr.exe",
        "https://github.com/ip7z/7zip/releases/download/24.09/7zr.exe",
    )
    打印信息("下载 7zr.exe 以便从安装包中抽出 Rar.exe (无需管理员)…")
    for 地址 in 地址表:
        try:
            _下载文件(地址, 目标)
            if 目标.is_file() and 目标.stat().st_size > 50_000:
                return 目标
        except Exception as 异常:  # noqa: BLE001
            打印警告(f"7zr 下载失败: {异常}")
    return None


def _用7z从安装包抽出Rar(安装包: 路径, 目标目录: 路径) -> 路径 | None:
    七z = _确保7z解压器()
    if 七z is None:
        return None
    目标目录.mkdir(parents=True, exist_ok=True)
    打印信息(f"用 {七z.name} 从安装包抽出 Rar.exe → {目标目录}")
    结果 = 子进程.run(
        [str(七z), "x", str(安装包), f"-o{目标目录}", "-y"],
        check=False,
        stdin=子进程.DEVNULL,
        stdout=子进程.PIPE,
        stderr=子进程.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if 结果.returncode != 0:
        打印警告(f"7z 解压返回 {结果.returncode}")
    for 名 in ("Rar.exe", "rar.exe", "Rar", "rar"):
        直达 = 目标目录 / 名
        if 直达.is_file() and _校验Rar能创建(直达):
            return 直达
    for 命中 in 目标目录.rglob("Rar.exe"):
        if 命中.is_file() and _校验Rar能创建(命中):
            return 命中
    for 命中 in 目标目录.rglob("rar.exe"):
        if 命中.is_file() and "unrar" not in 命中.name.lower() and _校验Rar能创建(命中):
            return 命中
    return None


def _通过官方安装包补Rar到Tools() -> 路径 | None:
    r"""
    下载含 Rar.exe 的安装包到 tools/cache, 优先无提权抽出到 tools/rar;
    静默安装仅作次选 (常需管理员, 失败则忽略)。
    """
    缓存目录 = _工具目录 / "cache"
    安装包 = 缓存目录 / _RAR安装包名
    打印信息("正在准备 RAR 创建端到 tools/ …")
    最后错误: Exception | None = None
    for 地址 in _RAR下载地址表:
        try:
            if not 安装包.is_file() or 安装包.stat().st_size < 1_000_000:
                打印信息(f"下载: {地址}")
                _下载文件(地址, 安装包)
            break
        except Exception as 异常:  # noqa: BLE001
            最后错误 = 异常
            打印警告(f"下载失败 ({异常}), 试下一源…")
            continue
    else:
        if 最后错误:
            打印警告(f"全部下载源失败: {最后错误}")
        return None

    if not 安装包.is_file():
        return None

    目标目录 = _便携Rar目录
    # 1) 无管理员: 7z 直接从安装包抽出
    抽出 = _用7z从安装包抽出Rar(安装包, 目标目录)
    if 抽出 is not None:
        return 抽出

    # 2) 次选静默安装 (可能 WinError 740 要提升)
    目标目录.mkdir(parents=True, exist_ok=True)
    安装目录 = str(目标目录.resolve())
    打印信息(f"尝试静默安装到 {安装目录} (若提示需要管理员将自动跳过)…")
    try:
        结果 = 子进程.run(
            [str(安装包), "/S", f"/D={安装目录}"],
            check=False,
            stdin=子进程.DEVNULL,
            stdout=子进程.PIPE,
            stderr=子进程.PIPE,
        )
    except OSError as 异常:
        打印警告(f"静默安装无法启动 ({异常})")
        结果 = None
    if 结果 is not None:
        for _ in range(20):
            for 名 in ("Rar.exe", "rar.exe"):
                候选 = 目标目录 / 名
                if 候选.is_file() and _校验Rar能创建(候选):
                    return 候选
            时间.sleep(0.3)
        for 命中 in 目标目录.rglob("Rar.exe"):
            if 命中.is_file() and _校验Rar能创建(命中):
                return 命中

    打印警告("未能从安装包得到可用的 Rar.exe")
    return None


def 查找Rar可执行文件() -> 路径:
    r"""兼容旧名: 仅探测, 找不到则失败 (测试可 mock)。"""
    已有 = _探测Rar可执行文件()
    if 已有 is not None:
        return 已有
    失败退出(
        "未找到可创建 RAR 的命令行工具。\n"
        "  请将 rar.exe 加入 PATH, 或放到 tools/rar/Rar.exe; 也可直接运行打包脚本让其自动补齐。"
    )
    raise AssertionError("不可达")


def 确保Rar可执行文件(状态: 打包进度 | None = None) -> 路径:
    r"""
    保证本机有能 `rar a` 写出 .rar 的工具:
    1) 探测 PATH / 常见目录 / tools
    2) 校验真正能创建 (排除 unrar)
    3) winget 补装 / 官方安装包静默装到 tools/rar
    """
    for 候选 in _枚举Rar候选():
        if _校验Rar能创建(候选):
            if 状态 is None or 状态.纯文本:
                打印信息(f"RAR 工具: {候选}")
            return 候选

    if 状态 is None or 状态.纯文本:
        打印警告("环境缺少可用的 rar 创建端, 开始自动补齐…")
    elif 状态:
        状态.进入阶段("压缩", "自动准备 RAR 工具…", 段内=0.02, 明细="bootstrap")

    if _通过Winget补Rar():
        for 候选 in _枚举Rar候选():
            if _校验Rar能创建(候选):
                打印成功(f"已通过 winget 就绪: {候选}")
                return 候选

    便携 = _通过官方安装包补Rar到Tools()
    if 便携 is not None:
        打印成功(f"已安装便携 RAR: {便携}")
        return 便携

    # 装完再扫一遍系统目录
    for 候选 in _枚举Rar候选():
        if _校验Rar能创建(候选):
            return 候选

    失败退出(
        "无法自动准备 RAR 创建工具, 发布包必须是 .rar。\n"
        "  可手动任选其一后重试:\n"
        "  · 安装任意提供 rar.exe 的工具, 并保证 `rar a` 可用\n"
        "  · 将 Rar.exe 放到: " + str(_便携Rar目录 / "Rar.exe") + "\n"
        "  · 或执行: winget install -e --id RARLab.WinRAR"
    )
    raise AssertionError("不可达")


def 打包为压缩包(绿色根: 路径, 版本: str, 状态: 打包进度 | None = None) -> 路径:
    r"""
    调用本机 rar 兼容命令行生成 .rar。
    包内顶层:
      · MyBiOut!/   绿色程序目录
      · README.txt
      · LICENSE
    输出到工程根/打包结果/「MyBiOut! <版本>.rar」(空格与 ! 保留)。
    环境缺 rar 时会自动检测并补齐 (tools/ 或 winget)。
    先写到临时名再替换, 避免半成品被当分发包。
    """
    if 状态 is None or 状态.纯文本:
        打印步骤(4, 4, "压缩为 rar 发布包")

    if not 绿色根.is_dir():
        说明 = f"绿色目录不存在: {绿色根}"
        if 状态 and not 状态.纯文本:
            状态.标记失败(说明)
        失败退出(说明)

    说明文件 = 工程根目录 / "README.txt"
    许可文件 = 工程根目录 / "LICENSE"
    简短说明 = (
        f"MyBiOut! v{版本}\n\n"
        "解压后，保持 MyBiOut! 文件夹完整，双击其中的 MyBiOut!.exe 启动。\n"
        "无需安装 Python；登录态和导出目录请在设置页自行配置。\n"
    )
    说明文件.write_text(简短说明, encoding="utf-8-sig")
    for 必备, 标签 in ((说明文件, "README.txt"), (许可文件, "LICENSE")):
        if not 必备.is_file():
            说明 = f"发布包必备文件缺失: {标签} ({必备})"
            if 状态 and not 状态.纯文本:
                状态.标记失败(说明)
            失败退出(说明)

    rar程序 = 确保Rar可执行文件(状态)

    发布目录 = 发布目录路径().resolve()
    发布目录.mkdir(parents=True, exist_ok=True)
    # 绝对路径, 避免 rar 在 OEM 代码页下处理中文版本号 / 空格路径失败
    基名 = 发布包基名(版本)
    归档文件 = (发布目录 / f"{基名}.rar").resolve()
    临时文件 = (发布目录 / f"{基名}.rar.part").resolve()
    if 临时文件.exists():
        安全删除文件(临时文件, 说明="清理上次未完成的 rar.part")
    if 归档文件.exists():
        安全删除文件(归档文件, 说明="覆盖同名旧 rar")

    文件列表 = 列举待拷文件(绿色根)
    总数 = max(1, len(文件列表) + 2)  # + README.txt + LICENSE
    if 状态:
        状态.进入阶段(
            "压缩",
            "RAR 打包中…",
            段内=0.05,
            明细=f"0/{总数} 文件",
            计量当前=0,
            计量总共=总数,
        )

    安静开关: list[str] = []
    if "rar" in rar程序.name.lower():
        安静开关 = ["-idq"]

    # 1) 绿色目录 → 包内 MyBiOut!/
    #    a 添加, -r 递归, -m3 压缩, -o+ 覆盖, -ap 包内路径前缀
    参数绿: list[str] = [
        str(rar程序),
        "a",
        "-r",
        "-m3",
        "-o+",
        *安静开关,
        f"-ap{产物显示名}",
        str(临时文件),
        "*",
    ]

    停止监视 = 线程.Event()

    def _监视体积() -> None:
        饱和 = max(80 * 1024 * 1024, 目录体积字节(绿色根) // 2)
        while not 停止监视.is_set():
            已 = 临时文件.stat().st_size if 临时文件.is_file() else 0
            段内 = 0.05 + 0.85 * min(1.0, 已 / max(1, 饱和))
            if 状态:
                状态.进入阶段(
                    "压缩",
                    "RAR 写入…",
                    段内=段内,
                    明细=f"{已 / (1024 * 1024):.0f} MB",
                )
            停止监视.wait(0.6)

    监视: 线程.Thread | None = None
    if 状态 is not None:
        监视 = 线程.Thread(target=_监视体积, daemon=True)
        监视.start()
    try:
        执行命令(参数绿, 工作目录=绿色根, 步骤说明="RAR 压缩程序目录", 状态=状态)
        if 状态:
            状态.进入阶段(
                "压缩",
                "附加 README.txt / LICENSE…",
                段内=0.92,
                明细="文档",
            )
        # 2) 根级文档: -ep1 只保留文件名, 与 MyBiOut!/ 并列
        参数文: list[str] = [
            str(rar程序),
            "a",
            "-m3",
            "-o+",
            *安静开关,
            "-ep1",
            str(临时文件),
            str(说明文件.resolve()),
            str(许可文件.resolve()),
        ]
        执行命令(参数文, 工作目录=工程根目录, 步骤说明="RAR 附加说明与许可", 状态=状态)
    finally:
        停止监视.set()
        if 监视 is not None:
            监视.join(timeout=2.0)

    if not 临时文件.is_file() or 临时文件.stat().st_size < 64:
        说明 = f"RAR 未生成有效文件: {临时文件}"
        if 状态 and not 状态.纯文本:
            状态.标记失败(说明)
        失败退出(说明)

    # 魔数: RAR 1.5+ / 5.0 均为 "Rar!" (52 61 72 21); 与体积无关, 非 RAR 一律拒绝
    头 = 临时文件.read_bytes()[:4]
    if 头 != b"Rar!":
        说明 = f"产物不像 RAR 文件 (文件头 {头!r}): {临时文件}"
        if 状态 and not 状态.纯文本:
            状态.标记失败(说明)
        失败退出(说明)

    try:
        临时文件.replace(归档文件)
    except OSError:
        文件工具.move(str(临时文件), str(归档文件))

    大小兆 = 归档文件.stat().st_size / 1024 / 1024
    if 状态 is None or 状态.纯文本:
        打印成功(f"发布包已生成: {归档文件}")
        打印信息(f"包内: {产物显示名}/ + README.txt + LICENSE")
        打印信息(f"文件大小约 {大小兆:.1f} MB")
        打印信息(f"压缩工具: {rar程序}")
    if 状态:
        状态.完成阶段("压缩", "压缩完成", 明细=f"{总数} 文件 / {大小兆:.1f} MB")
    return 归档文件


def 格式化耗时(秒: float) -> str:
    秒 = max(0.0, float(秒))
    if 秒 < 60:
        return f"{秒:.1f} 秒"
    分 = int(秒 // 60)
    余 = 秒 - 分 * 60
    if 分 < 60:
        return f"{分} 分 {余:.0f} 秒"
    时 = 分 // 60
    分 = 分 % 60
    return f"{时} 时 {分} 分 {余:.0f} 秒"


def 执行完整打包(状态: 打包进度) -> None:
    r"""在后台线程或主线程调用；通过 状态 汇报进度。"""
    旧版本 = 状态.旧版本
    新版本 = 状态.新版本
    状态.打点开始()
    锁句柄 = None
    try:
        锁句柄 = 获取打包互斥锁(状态)
        清理打包残留(状态, 阶段="开工")

        状态.进入阶段("版本", f"写入版本 {旧版本} → {新版本}", 段内=0.3, 明细=新版本)
        写入版本文件(新版本)
        状态.完成阶段("版本", f"版本 {新版本}", 明细=新版本)
        if 状态.纯文本:
            打印成功(f"已写入版本文件: {版本文件路径}")

        安装依赖(状态)
        执行构建(状态)
        绿色根 = 组装绿色目录(新版本, 状态)
        归档 = 打包为压缩包(绿色根, 新版本, 状态)
        清理打包残留(状态, 阶段="收尾", 保留版本=新版本)
        大小兆 = 归档.stat().st_size / 1024 / 1024
        状态.标记成功(绿色根=绿色根, 归档=归档, 大小兆=大小兆)
        if 状态.纯文本:
            打印标题("搞定了!")
            print(f"  版本号:   v{新版本}")
            print(f"  绿色目录: {绿色根}")
            print(f"  发布文件: {归档}")
            print(f"  耗时:     {格式化耗时(状态.耗时秒)}")
            print()
            # 纯文本模式同样: 按任意键 → 真关机
            if 系统.stdout and getattr(系统.stdout, "isatty", lambda: False)():
                _等待任意键("按任意键关机…")
                _真关机()
    except SystemExit as 退出:
        if not 状态.已结束:
            状态.标记失败(f"退出码 {退出.code}")
        if 状态.纯文本:
            raise
    except Exception as 异常:  # noqa: BLE001
        原因 = str(异常) or 异常.__class__.__name__
        状态.标记失败(原因)
        if 状态.纯文本:
            失败退出(f"未预期异常: {原因}")
    finally:
        释放打包互斥锁(锁句柄)


# ---------- 主流程 ----------

_帮助文本: str = (
    "用法:\n"
    "  python 打包.py        正常打包 (本月甲…丑 递增, 满 12 坠机)\n"
    "  python 打包.py 重来   版本计时归零, 下次从本月「甲」起算\n"
    "  python 打包.py 帮助   显示本说明\n"
)


def 解析命令行() -> str:
    r"""
    :return: 动作键 — \"打包\" | \"重来\"
    """
    参数列表 = 系统.argv[1:]
    if not 参数列表:
        return "打包"
    if len(参数列表) == 1 and 参数列表[0] in {"-h", "--help", "帮助", "/?"}:
        print(_帮助文本)
        raise SystemExit(0)
    if len(参数列表) == 1 and 参数列表[0] in {"重来", "reset", "--reset"}:
        return "重来"
    失败退出(f"无法识别的参数: {' '.join(参数列表)}\n{_帮助文本}")
    raise AssertionError("不可达")


def 执行重来命令() -> None:
    r"""只改 version.txt, 不跑构建。"""
    旧版本 = 读取当前版本()
    下次甲 = 重来本月从甲()
    打印标题("版本计时 · 重来")
    打印信息(f"当前: {旧版本}")
    打印成功(f"已归零, 下次打包将从「{下次甲}」起算")
    打印信息(f"已写入: {版本文件路径}")
    打印信息("接着执行:  python 打包.py")
    print()


def 主程序() -> None:
    配置控制台编码()
    动作 = 解析命令行()
    检查运行平台()

    if 动作 == "重来":
        执行重来命令()
        return

    旧版本 = 读取当前版本()
    新版本 = 计算下一版本(旧版本)
    用TUI = 可否播放动画()

    状态 = 打包进度(
        旧版本=旧版本,
        新版本=新版本,
        纯文本=not 用TUI,
    )
    状态.进入阶段("版本", "准备中…", 段内=0.0)

    if not 用TUI:
        打印标题("MyBiOut! 绿色版一键打包")
        if not (系统.stdout and getattr(系统.stdout, "isatty", lambda: False)()):
            打印信息("非交互终端，使用纯文本提示")
        打印信息(f"工程根目录: {工程根目录}")
        打印信息(f"Python: {系统.executable}")
        打印步骤(0, 4, "准备版本号")
        打印信息(f"当前版本: {旧版本}")
        打印信息(f"本次版本: {新版本}")

    已回滚 = False

    if 用TUI:
        try:
            运行进度TUI(状态, 开工=lambda: 执行完整打包(状态))
        except Exception as 异常:  # noqa: BLE001
            打印警告(f"TUI 异常，改文本模式: {异常}")
            if not 状态.已结束:
                执行完整打包(状态)

        if not 状态.已成功:
            写入版本文件(旧版本)
            已回滚 = True
            打印警告(f"打包未完成，版本号已回滚为: {旧版本}")
            raise SystemExit(1)
        return

    try:
        执行完整打包(状态)
        if not 状态.已成功:
            raise SystemExit(1)
    finally:
        if not 状态.已成功 and not 已回滚:
            写入版本文件(旧版本)
            打印警告(f"打包未完成，版本号已回滚为: {旧版本}")


if __name__ == "__main__":
    主程序()
