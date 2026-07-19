r"""
MyBiOut! 主入口模块, 解析命令行参数并启动 FastAPI 服务
支持绿色版内嵌 Web 窗口 (pywebview) 与传统浏览器模式

:file: mybiout/main.py
:author: WaterRun
:time: 2026-04-02
"""

import argparse as 参数解析
import math as 数学
import random as 随机
import shutil as 文件工具
import socket as 套接字
import sys as 系统
import threading as 线程
import time as 时间
import webbrowser as 浏览器
from contextlib import suppress as 忽略异常
from dataclasses import dataclass as 数据类
from dataclasses import field as 字段
from pathlib import Path as 路径

import uvicorn as 服务运行器

from mybiout.pages.utils import 是否冻结运行
from mybiout.pages.utils import 取工具目录
from mybiout.pages.utils import 取端口


class _中文参数解析器(参数解析.ArgumentParser):
    def format_help(自身) -> str:
        return (
            super()
            .format_help()
            .replace("usage:", "用法:")
            .replace("options:", "选项:")
            .replace("show this help message and exit", "显示此帮助并退出")
        )


_控制序列引导: str = "\033["
_隐藏光标: str = f"{_控制序列引导}?25l"
_显示光标: str = f"{_控制序列引导}?25h"
_清屏: str = f"{_控制序列引导}2J{_控制序列引导}H"
_重置样式: str = f"{_控制序列引导}0m"
_加粗样式: str = f"{_控制序列引导}1m"

_盲文低密度: str = "⠁⠂⠄⡀⠈⠐⠠⢀"
_盲文中密度: str = "⠃⠅⠆⠉⠊⠌⠑⠒⠔⡁⡂⡄⡈⡐⡠⢁⢂⢄⢈⢐⢠⣀"
_盲文高密度: str = "⠿⡿⢿⣿⣾⣽⣻⣷⣯⣟⡷⡯⡟⠷⠯⠟⣶⣵⣳"
_闪光字符: str = "✦✧⋆˚✩✫✬✮✰⊹✵✺❖"
_最大粒子数: int = 280


def _取程序工具目录() -> 路径:
    r"""
    获取 bin 工具目录 (绿色旁路优先)
    :return: Path: bin 目录
    """
    return 取工具目录()


def _配置文本输出() -> None:
    r"""
    避免控制台/冻结包 stdout 在 GBK 下打印 ✦ 等字符直接崩掉。
    windowed 启动时 stdout 可能是包装流, reconfigure 不一定生效, 故打印侧另有 _安全打印。
    """
    for 输出流 in (系统.stdout, 系统.stderr):
        if 输出流 is None:
            continue
        重配函数 = getattr(输出流, "reconfigure", None)
        if 重配函数 is None:
            continue
        with 忽略异常(TypeError, ValueError, OSError, AttributeError):
            重配函数(encoding="utf-8", errors="replace")
        with 忽略异常(TypeError, ValueError, OSError, AttributeError):
            重配函数(errors="replace")


def _安全打印(*参数: object, **关键字: object) -> None:
    r"""print 的容错包装: 编码失败时降级为 ASCII 可表示文本。"""
    try:
        print(*参数, **关键字)
        return
    except UnicodeEncodeError:
        pass
    except Exception:
        return
    try:
        文本 = " ".join(str(x) for x in 参数)
        文本 = 文本.encode("gbk", errors="replace").decode("gbk", errors="replace")
        print(文本, **{k: v for k, v in 关键字.items() if k != "file"})
    except Exception:
        with 忽略异常(Exception):
            print(repr(参数))


def _是否有交互控制台() -> bool:
    r"""
    判断 stdout 是否为可交互终端 (windowed 冻结包通常无控制台)
    """
    输出 = 系统.stdout
    if 输出 is None:
        return False
    try:
        return bool(输出.isatty())
    except Exception:
        return False


def _提示致命错误(消息: str, *, 标题: str = "MyBiOut!") -> None:
    r"""
    输出致命错误; 冻结且无控制台时用系统消息框, 避免 --windowed 静默失败
    """
    with 忽略异常(Exception):
        _安全打印(消息)
    if not 是否冻结运行() or _是否有交互控制台():
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, 消息, 标题, 0x10)
    except Exception:
        pass


# ===== 环境检查 =====


@数据类(frozen=True, slots=True)
class _环境项:
    r"""
    单项环境检查结果
    """

    名称: str
    可用: bool
    提示: str


def _检查环境() -> list[_环境项]:
    r"""
    检查运行环境中各必需依赖项的可用性
    :return: list[_环境项]: 检查结果列表
    """
    检查结果: list[_环境项] = []

    程序工具目录: 路径 = _取程序工具目录()

    # ffmpeg
    找到FFmpeg: bool = 文件工具.which("ffmpeg") is not None
    if not 找到FFmpeg:
        for 候选路径 in (
            程序工具目录 / "BBDown" / "ffmpeg.exe",
            程序工具目录 / "BBDown" / "ffmpeg",
            程序工具目录 / "ffmpeg.exe",
            程序工具目录 / "ffmpeg",
            程序工具目录 / "ffmpeg" / "ffmpeg.exe",
            程序工具目录 / "ffmpeg" / "bin" / "ffmpeg.exe",
        ):
            if 候选路径.exists():
                找到FFmpeg = True
                break
    检查结果.append(
        _环境项(
            "ffmpeg",
            找到FFmpeg,
            "下载: https://ffmpeg.org/download.html\n"
            "      下载后将 ffmpeg.exe 所在目录添加至系统 PATH 环境变量\n"
            "      或将 ffmpeg.exe 放入绿色包/程序目录的 bin/ 下",
        )
    )

    # BBDown
    找到BBDown: bool = 文件工具.which("BBDown") is not None or 文件工具.which("bbdown") is not None
    if not 找到BBDown:
        for 候选路径 in (
            程序工具目录 / "BBDown" / "BBDown.exe",
            程序工具目录 / "BBDown" / "BBDown",
            程序工具目录 / "BBDown.exe",
            程序工具目录 / "BBDown",
        ):
            if 候选路径.exists():
                找到BBDown = True
                break
    检查结果.append(
        _环境项(
            "BBDown",
            找到BBDown,
            "下载: https://github.com/nilaoda/BBDown/releases\n"
            "      将 BBDown 可执行文件放入系统 PATH 或绿色包/程序目录的 bin/ 下",
        )
    )

    # biliffm4s
    找到biliffm4s: bool = False
    try:
        import biliffm4s  # noqa: F401

        找到biliffm4s = True
    except ImportError:
        ...
    检查结果.append(
        _环境项(
            "biliffm4s",
            找到biliffm4s,
            "安装: pip install biliffm4s\n      仓库: https://github.com/Water-Run/-m4s-Python-biliffm4s",
        )
    )

    return 检查结果


def _打印环境详情(检查列表: list[_环境项]) -> None:
    r"""
    在终端打印环境检查详细报告
    :param 检查列表: 检查结果列表
    """
    print()
    print("  ── 环境检查 ──")
    for 检查项 in 检查列表:
        图标: str = "✅" if 检查项.可用 else "❌"
        状态: str = "就绪" if 检查项.可用 else "未找到"
        print(f"  {图标} {检查项.名称:<12} {状态}")
        if not 检查项.可用:
            for 提示行 in 检查项.提示.split("\n"):
                print(f"      {提示行.strip()}")
    print()
    print("  请安装全部缺失组件后重新启动 MyBiOut!")
    print()


def _取启动阻断项(_检查列表: list[_环境项]) -> list[_环境项]:
    r"""
    返回会阻止 Web 服务启动的环境问题。

    BBDown、ffmpeg、biliffm4s 都只影响具体功能页，不能阻断配置页、
    Markdown 导出页或环境诊断接口的访问。
    """
    return []


# ===== 服务启动状态 =====


@数据类(slots=True)
class _服务启动状态:
    r"""
    Uvicorn 后台启动状态
    """

    已启动: 线程.Event = 字段(default_factory=线程.Event)
    已失败: 线程.Event = 字段(default_factory=线程.Event)
    原因: str = ""
    锁: 线程.Lock = 字段(default_factory=线程.Lock)
    服务: 服务运行器.Server | None = None
    线程对象: 线程.Thread | None = None

    def 标记已启动(自身) -> None:
        r"""
        标记服务已启动
        """
        with 自身.锁:
            if 自身.已失败.is_set():
                return
            自身.已启动.set()

    def 标记失败(自身, 原因: str) -> None:
        r"""
        标记服务启动失败
        :param 原因: 失败原因
        """
        with 自身.锁:
            if 自身.已启动.is_set() or 自身.已失败.is_set():
                return
            自身.原因 = 原因
            自身.已失败.set()


def _探测端口绑定错误(端口: int) -> str | None:
    r"""
    预探测端口是否可绑定
    :param 端口: 端口号
    :return: str | None: 可用返回 None，不可用返回错误原因
    """
    try:
        with 套接字.socket(套接字.AF_INET, 套接字.SOCK_STREAM) as 套接字对象:
            套接字对象.bind(("127.0.0.1", 端口))
    except OSError as e:
        详细原因: str = e.strerror or str(e)
        return f"端口 {端口} 不可用: {详细原因}"
    return None


def _后台启动服务(端口: int) -> _服务启动状态:
    r"""
    后台启动 Uvicorn，并异步监控启动结果
    :param 端口: 服务端口号
    :return: _服务启动状态: 启动状态对象
    """
    状态: _服务启动状态 = _服务启动状态()

    if 端口错误 := _探测端口绑定错误(端口):
        状态.标记失败(端口错误)
        return 状态

    配置: 服务运行器.Config = 服务运行器.Config(
        "mybiout.pages.apis:应用",
        host="127.0.0.1",
        port=端口,
        log_level="warning",
    )
    服务: 服务运行器.Server = 服务运行器.Server(配置)
    状态.服务 = 服务

    def _运行服务() -> None:
        r"""
        后台线程执行 server.run()
        """
        try:
            服务.run()
        except Exception as e:
            状态.标记失败(f"Uvicorn 启动异常: {e}")

    后台线程: 线程.Thread = 线程.Thread(target=_运行服务, daemon=True)
    状态.线程对象 = 后台线程
    后台线程.start()

    def _监控启动() -> None:
        r"""
        监控 server.started 与线程生命周期，判定启动成功/失败
        """
        截止时间: float = 时间.monotonic() + 20.0
        while 时间.monotonic() < 截止时间:
            if 状态.已失败.is_set():
                return
            if 服务.started:
                状态.标记已启动()
                return
            if not 后台线程.is_alive():
                状态.标记失败("服务线程提前退出（可能端口占用或应用初始化失败）")
                return
            时间.sleep(0.03)

        if 服务.started:
            状态.标记已启动()
            return

        状态.标记失败("服务启动超时")
        服务.should_exit = True

    线程.Thread(target=_监控启动, daemon=True).start()
    return 状态


def _等待服务启动(状态: _服务启动状态, 超时: float = 25.0) -> bool:
    r"""
    等待服务启动成功或失败
    :param 状态: 启动状态对象
    :param 超时: 最大等待秒数
    :return: bool: True=成功, False=失败或超时
    """
    截止时间: float = 时间.monotonic() + 超时
    while 时间.monotonic() < 截止时间:
        if 状态.已启动.is_set():
            return True
        if 状态.已失败.is_set():
            return False
        时间.sleep(0.05)
    return 状态.已启动.is_set()


# ===== 终端动画工具 =====


def _定位(行: int, 列: int) -> str:
    r"""
    生成终端光标定位控制序列
    :param 行: 行号, 1-based
    :param 列: 列号, 1-based
    :return: str: ANSI 控制序列
    """
    return f"{_控制序列引导}{行};{列}H"


def _前景色(红: int, 绿: int, 蓝: int) -> str:
    r"""
    生成 24-bit 真彩前景色 ANSI 控制序列
    :param 红: 红色分量
    :param 绿: 绿色分量
    :param 蓝: 蓝色分量
    :return: str: ANSI 控制序列
    """
    return f"{_控制序列引导}38;2;{红};{绿};{蓝}m"


def _线性插值(起值: tuple[int, int, int], 止值: tuple[int, int, int], 比例: float) -> tuple[int, int, int]:
    r"""
    对 RGB 颜色做线性插值
    :param 起值: 起始颜色
    :param 止值: 结束颜色
    :param 比例: 插值比例, 自动钳制到 [0.0, 1.0]
    :return: tuple[int, int, int]: 插值后的颜色
    """
    钳制比例: float = max(0.0, min(1.0, 比例))
    return (
        int(起值[0] + (止值[0] - 起值[0]) * 钳制比例),
        int(起值[1] + (止值[1] - 起值[1]) * 钳制比例),
        int(起值[2] + (止值[2] - 起值[2]) * 钳制比例),
    )


def _淡化(颜色值: tuple[int, int, int], 透明度: float) -> tuple[int, int, int]:
    r"""
    将颜色按比例淡化到黑色
    :param 颜色值: 原始颜色
    :param 透明度: 强度比例, 自动钳制到 [0.0, 1.0]
    :return: tuple[int, int, int]: 淡化后的颜色
    """
    强度: float = max(0.0, min(1.0, 透明度))
    return int(颜色值[0] * 强度), int(颜色值[1] * 强度), int(颜色值[2] * 强度)


def _中日韩宽度(文本: str) -> int:
    r"""
    估算字符串在终端中的显示宽度, CJK 字符按 2 列计
    :param 文本: 输入文本
    :return: int: 显示宽度
    """
    return sum(
        2
        if (
            0x2E80 <= ord(字符) <= 0x9FFF
            or 0xF900 <= ord(字符) <= 0xFAFF
            or 0xFF00 <= ord(字符) <= 0xFF60
            or 0x20000 <= ord(字符) <= 0x2FA1F
        )
        else 1
        for 字符 in 文本
    )


@数据类(frozen=True, slots=True)
class _主题:
    r"""
    动画配色主题
    """

    渐变甲: tuple[int, int, int]
    渐变乙: tuple[int, int, int]
    辅色组: tuple[tuple[int, int, int], ...]
    直升机色: tuple[int, int, int]
    星空色组: tuple[tuple[int, int, int], ...]


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

_旋翼帧: tuple[str, ...] = (
    "        ════╦════        ",
    "      ══════╬══════      ",
    "    ════════╬════════    ",
    "      ══════╬══════      ",
)
_机身帧: tuple[str, ...] = (
    "            ║            ",
    "       ╭────╨────╮       ",
    "═══════╡  ◉   ◉  ╞═══>   ",
    "       ╰──┬───┬──╯       ",
    "          ╰─╯ ╰─╯        ",
)
_直升机宽度: int = max(*(len(帧行) for 帧行 in _旋翼帧), *(len(帧行) for 帧行 in _机身帧))
_直升机高度: int = 1 + len(_机身帧)

_标题字形: tuple[str, ...] = (
    r"  __  __       ____  _  ___        _   _ ",
    r" |  \/  |_   _| __ )(_)/ _ \ _   _| |_| |",
    r" | |\/| | | | |  _ \| | | | | | | | __| |",
    r" | |  | | |_| | |_) | | |_| | |_| | |_|_|",
    r" |_|  |_|\__, |____/|_|\___/ \__,_|\__(_)",
    r"         |___/                          ! ",
)
_标题宽度: int = max(len(标题行) for 标题行 in _标题字形)


@数据类(slots=True)
class _粒子:
    r"""
    粒子对象, 用于盲文特效
    """

    横坐标: float
    纵坐标: float
    横速度: float
    纵速度: float
    寿命: float
    最大寿命: float
    颜色: tuple[int, int, int]

    def 步进(自身, 步长: float) -> bool:
        r"""
        推进粒子物理状态
        :param 步长: 时间步长
        :return: bool: 是否仍存活
        """
        自身.横坐标 += 自身.横速度 * 步长
        自身.纵坐标 += 自身.纵速度 * 步长
        自身.纵速度 += 3.5 * 步长
        自身.寿命 -= 步长
        return 自身.寿命 > 0

    @property
    def 字符(自身) -> str:
        r"""
        获取当前寿命对应的盲文字符密度
        :return: str: 单字符
        """
        比例值: float = 自身.寿命 / 自身.最大寿命 if 自身.最大寿命 > 0 else 0.0
        if 比例值 > 0.6:
            return 随机.choice(_盲文高密度)
        if 比例值 > 0.25:
            return 随机.choice(_盲文中密度)
        return 随机.choice(_盲文低密度)

    @property
    def 可见颜色(自身) -> tuple[int, int, int]:
        r"""
        获取当前可见颜色
        :return: tuple[int, int, int]: RGB 颜色
        """
        比例值: float = 自身.寿命 / 自身.最大寿命 if 自身.最大寿命 > 0 else 0.0
        return _淡化(自身.颜色, 比例值)


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
    r"""
    在指定位置生成爆发粒子
    :param 粒子池: 粒子池
    :param 横坐标: 爆发中心横坐标
    :param 纵坐标: 爆发中心纵坐标
    :param 数量: 粒子数量
    :param 颜色组: 颜色集合
    :param 速度: 初速度上限
    :param 寿命: 生命周期范围
    :param 散布: 初始位置离散半径
    """
    for _ in range(数量):
        角度: float = 随机.uniform(0.0, 数学.tau)
        速度绝对值: float = 随机.uniform(速度 * 0.3, 速度)
        存活时间: float = 随机.uniform(*寿命)
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


def _播放动画(端口: int, 启动状态: _服务启动状态 | None = None) -> None:
    r"""
    播放启动动画序列
    :param 端口: 服务端口号
    :param 启动状态: 服务启动状态对象（可选）
    :raise RuntimeError: 终端尺寸过小时抛出
    """
    宽度, 高度 = 文件工具.get_terminal_size((80, 24))
    if 宽度 < 52 or 高度 < 18:
        raise RuntimeError("终端尺寸过小, 跳过动画")

    主题: _主题 = 随机.choice(_主题表)
    随机源: 随机.Random = 随机.Random()
    输出缓冲: list[str] = []

    def 写入(文本: str) -> None:
        r"""
        向输出缓冲写入字符串
        """
        输出缓冲.append(文本)

    def 刷新输出() -> None:
        r"""
        刷新输出缓冲到终端
        """
        系统.stdout.write("".join(输出缓冲))
        系统.stdout.flush()
        输出缓冲.clear()

    def 绘制(
        行: int,
        列: int,
        文本: str,
        颜色: tuple[int, int, int] | None = None,
        加粗: bool = False,
    ) -> None:
        r"""
        在终端指定位置绘制文本
        :param 行: 行号, 1-based
        :param 列: 列号, 1-based
        :param 文本: 输出文本
        :param 颜色: RGB 颜色
        :param 加粗: 是否加粗
        """
        if 行 < 1 or 行 > 高度 or 列 > 宽度:
            return
        裁剪文本: str = 文本[: 宽度 - 列 + 1]
        if not 裁剪文本:
            return
        负载: str = _定位(行, 列)
        if 加粗:
            负载 += _加粗样式
        if 颜色 is not None:
            负载 += _前景色(*颜色)
        写入(负载 + 裁剪文本 + _重置样式)

    def 清行(行: int, 起列: int = 1, 止列: int | None = None) -> None:
        r"""
        清空指定行区间
        :param 行: 行号
        :param 起列: 起始列
        :param 止列: 结束列, 为空时到行尾
        """
        if 行 < 1 or 行 > 高度:
            return
        结束列: int = min(止列 or 宽度, 宽度)
        长度: int = 结束列 - 起列 + 1
        if 长度 > 0:
            写入(_定位(行, max(1, 起列)) + " " * 长度)

    写入(_隐藏光标 + _清屏)
    刷新输出()

    星点数量: int = 随机源.randint(宽度 * 高度 // 35, 宽度 * 高度 // 16)
    星空色组: list[tuple[int, int, str, tuple[int, int, int]]] = [
        (
            随机源.randint(1, 高度),
            随机源.randint(1, 宽度),
            随机源.choice(_盲文低密度 + "·.˙"),
            随机源.choice(主题.星空色组),
        )
        for _ in range(星点数量)
    ]
    随机源.shuffle(星空色组)
    批量: int = max(1, len(星空色组) // 8)
    for 索引 in range(0, len(星空色组), 批量):
        for 星行, 星列, 星字符, 星颜色 in 星空色组[索引 : 索引 + 批量]:
            绘制(星行, 星列, 星字符, 颜色=星颜色)
        刷新输出()
        时间.sleep(0.02)

    基准行: int = max(3, 高度 // 4)
    波幅: float = 随机源.uniform(0.3, 1.8)
    波频: float = 随机源.uniform(1.0, 3.0)
    帧数: int = 58 + 随机源.randint(-8, 10)
    步长: float = 0.032
    粒子列表: list[_粒子] = []
    前行: int = 基准行
    前列: int = 宽度 + 6
    哔哩行: int = min(基准行 + _直升机高度 + 2, 高度 - 2)
    已哔哩爆发: bool = False

    def _坠机动画(直升机列: int, 直升机行: int, 原因文本: str) -> None:
        r"""
        启动失败时的坠机动画
        :param 直升机列: 当前直升机列
        :param 直升机行: 当前直升机行
        :param 原因文本: 失败原因
        """
        坠毁色组: tuple[tuple[int, int, int], ...] = ((255, 200, 80), (255, 120, 60), (255, 70, 70))
        当前列: int = 直升机列
        当前行: int = 直升机行
        本轮前行: int = 直升机行
        本轮前列: int = 直升机列

        for 步进 in range(18):
            for 行偏移 in range(_直升机高度):
                清行(本轮前行 + 行偏移, max(1, 本轮前列), min(宽度, 本轮前列 + _直升机宽度 + 3))

            当前列 = min(宽度 - _直升机宽度, 当前列 + 1 + (1 if 步进 > 10 else 0))
            当前行 = min(高度 - _直升机高度 - 1, 当前行 + 1)

            _爆发粒子(
                粒子列表,
                当前列 + _直升机宽度 * 0.45,
                当前行 + _直升机高度 * 0.75,
                10 + 步进 // 2,
                坠毁色组,
                速度=8.0,
                寿命=(0.25, 0.9),
                散布=1.5,
            )

            粒子列表[:] = [粒子 for 粒子 in 粒子列表 if 粒子.步进(0.045)]
            for 粒子 in 粒子列表:
                粒子列: int = int(粒子.横坐标)
                粒子行: int = int(粒子.纵坐标)
                if 1 <= 粒子行 <= 高度 and 1 <= 粒子列 <= 宽度:
                    绘制(粒子行, 粒子列, 粒子.字符, 颜色=粒子.可见颜色)

            旋翼: str = _旋翼帧[步进 % len(_旋翼帧)]
            for 列索引, 字符 in enumerate(旋翼):
                列: int = 当前列 + 列索引
                if 字符 != " ":
                    绘制(当前行, 列, 字符, 颜色=(255, 120, 80), 加粗=True)

            for 机身行索引, 行文本 in enumerate(_机身帧):
                行: int = 当前行 + 1 + 机身行索引
                for 列索引, 字符 in enumerate(行文本):
                    列: int = 当前列 + 列索引
                    if 字符 != " ":
                        绘制(行, 列, 字符, 颜色=(255, 90, 90), 加粗=True)

            本轮前行, 本轮前列 = 当前行, 当前列
            刷新输出()
            时间.sleep(0.03)

        _爆发粒子(
            粒子列表,
            当前列 + _直升机宽度 * 0.5,
            当前行 + _直升机高度 * 0.8,
            85,
            ((255, 230, 120), (255, 150, 80), (255, 80, 80)),
            速度=10.0,
            寿命=(0.3, 1.3),
            散布=2.5,
        )

        for _ in range(22):
            粒子列表[:] = [粒子 for 粒子 in 粒子列表 if 粒子.步进(0.05)]
            for 粒子 in 粒子列表:
                粒子列: int = int(粒子.横坐标)
                粒子行: int = int(粒子.纵坐标)
                if 1 <= 粒子行 <= 高度 and 1 <= 粒子列 <= 宽度:
                    绘制(粒子行, 粒子列, 粒子.字符, 颜色=粒子.可见颜色)
            刷新输出()
            时间.sleep(0.025)

        标题: str = "✖ Man!"
        原因行: str = f"孩子: {原因文本 or '未知错误'}"
        if len(原因行) > max(12, 宽度 - 4):
            原因行 = 原因行[: max(9, 宽度 - 7)] + "..."

        标题行: int = max(2, 高度 // 2 - 1)
        清行(标题行, 1, 宽度)
        清行(标题行 + 1, 1, 宽度)
        绘制(标题行, max(1, (宽度 - len(标题)) // 2), 标题, 颜色=(255, 90, 90), 加粗=True)
        绘制(标题行 + 1, max(1, (宽度 - len(原因行)) // 2), 原因行, 颜色=(255, 200, 120), 加粗=True)
        刷新输出()
        时间.sleep(0.35)

    for 帧 in range(帧数):
        比例: float = 帧 / 帧数
        直升机列: int = int((宽度 + 6) + ((-_直升机宽度 - 6) - (宽度 + 6)) * 比例)
        直升机行: int = int(基准行 + 波幅 * 数学.sin(波频 * 比例 * 数学.tau))

        if 启动状态 is not None and 启动状态.已失败.is_set():
            _坠机动画(直升机列, 直升机行, 启动状态.原因)
            raise RuntimeError(启动状态.原因 or "服务启动失败")

        for 行偏移 in range(_直升机高度):
            清行(前行 + 行偏移, max(1, 前列), min(宽度, 前列 + _直升机宽度 + 2))

        粒子列表 = [粒子 for 粒子 in 粒子列表 if 粒子.步进(步长)]
        for 粒子 in 粒子列表:
            粒子列: int = int(粒子.横坐标)
            粒子行: int = int(粒子.纵坐标)
            if 1 <= 粒子行 <= 高度 and 1 <= 粒子列 <= 宽度:
                绘制(粒子行, 粒子列, 粒子.字符, 颜色=粒子.可见颜色)

        尾焰列: float = float(直升机列 + _直升机宽度 - 2)
        尾焰行: float = float(直升机行 + 3)
        for _ in range(随机源.randint(4, 9)):
            存活时间: float = 随机源.uniform(0.3, 1.1)
            粒子列表.append(
                _粒子(
                    横坐标=尾焰列 + 随机源.uniform(0.0, 2.4),
                    纵坐标=尾焰行 + 随机源.uniform(-0.6, 0.6),
                    横速度=随机源.uniform(1.2, 6.5),
                    纵速度=随机源.uniform(-1.0, 1.0),
                    寿命=存活时间,
                    最大寿命=存活时间,
                    颜色=随机源.choice(主题.辅色组),
                ),
            )
        if len(粒子列表) > _最大粒子数:
            del 粒子列表[: len(粒子列表) - _最大粒子数]

        旋翼: str = _旋翼帧[帧 % len(_旋翼帧)]
        for 列索引, 字符 in enumerate(旋翼):
            列: int = 直升机列 + 列索引
            if 1 <= 列 <= 宽度 and 1 <= 直升机行 <= 高度 and 字符 != " ":
                绘制(直升机行, 列, 字符, 颜色=主题.直升机色, 加粗=True)

        for 机身行索引, 行文本 in enumerate(_机身帧):
            行: int = 直升机行 + 1 + 机身行索引
            for 列索引, 字符 in enumerate(行文本):
                列: int = 直升机列 + 列索引
                if 1 <= 列 <= 宽度 and 1 <= 行 <= 高度 and 字符 != " ":
                    绘制(行, 列, 字符, 颜色=主题.直升机色, 加粗=True)

        if not 已哔哩爆发 and abs(直升机列 + _直升机宽度 // 2 - 宽度 // 2) < 8:
            已哔哩爆发 = True
            _爆发粒子(
                粒子列表,
                宽度 / 2,
                哔哩行,
                42,
                主题.辅色组,
                速度=9.0,
                寿命=(0.5, 2.0),
                散布=5.0,
            )

        前行, 前列 = 直升机行, 直升机列
        刷新输出()
        时间.sleep(步长)

    for _ in range(16):
        粒子列表 = [粒子 for 粒子 in 粒子列表 if 粒子.步进(0.06)]
        for 粒子 in 粒子列表:
            粒子列: int = int(粒子.横坐标)
            粒子行: int = int(粒子.纵坐标)
            if 1 <= 粒子行 <= 高度 and 1 <= 粒子列 <= 宽度:
                绘制(粒子行, 粒子列, 粒子.字符, 颜色=粒子.可见颜色)
        刷新输出()
        时间.sleep(0.032)

    哔哩文本: str = "哔 哩 哔 哩"
    if 1 <= 哔哩行 <= 高度:
        文本宽度: int = _中日韩宽度(哔哩文本)
        起始列: int = max(1, (宽度 - 文本宽度) // 2)
        当前文本列: int = 起始列
        for 字符 in 哔哩文本:
            字符宽度: int = 2 if ord(字符) > 0x7F else 1
            if 字符 != " " and 当前文本列 + 字符宽度 - 1 <= 宽度:
                for _ in range(3):
                    绘制(哔哩行, 当前文本列, 随机源.choice(_盲文高密度), 颜色=随机源.choice(主题.辅色组), 加粗=True)
                    刷新输出()
                    时间.sleep(0.016)
                绘制(哔哩行, 当前文本列, 字符, 颜色=随机源.choice(主题.辅色组), 加粗=True)
                刷新输出()
                时间.sleep(0.035)
            当前文本列 += 字符宽度

    时间.sleep(0.24)

    擦除模式: str = 随机源.choice(("down", "up", "center", "split"))
    行顺序: list[int] = list(range(1, 高度 + 1))
    match 擦除模式:
        case "up":
            行顺序.reverse()
        case "center":
            中线: int = 高度 // 2
            行顺序.sort(key=lambda 红: abs(红 - 中线))
        case "split":
            上半部: list[int] = list(range(1, 高度 // 2 + 1))
            下半部: list[int] = list(range(高度, 高度 // 2, -1))
            行顺序 = [红 for 成对行 in zip(上半部, 下半部, strict=False) for 红 in 成对行]
            行顺序 += 上半部[len(下半部) :] or 下半部[len(上半部) :]
        case _:
            ...

    for 行 in 行顺序:
        行文本: str = "".join(随机源.choice(_盲文中密度) for _ in range(宽度))
        绘制(行, 1, 行文本, 颜色=_线性插值(主题.渐变甲, 主题.渐变乙, 行 / 高度))
        if 行 % 2 == 0:
            刷新输出()
            时间.sleep(0.005)
    刷新输出()
    时间.sleep(0.06)

    for 行 in 行顺序:
        清行(行)
        if 行 % 3 == 0:
            刷新输出()
            时间.sleep(0.0025)
    刷新输出()

    标题上边: int = max(2, 高度 // 2 - len(_标题字形) // 2 - 4)
    标题左边: int = max(1, (宽度 - _标题宽度) // 2)

    for 序号, 行文本 in enumerate(_标题字形):
        行: int = 标题上边 + 序号
        if 行 > 高度:
            break
        for 列索引, 字符 in enumerate(行文本):
            列: int = 标题左边 + 列索引
            if 字符 != " " and 1 <= 列 <= 宽度:
                绘制(行, 列, 随机源.choice(_盲文高密度), 颜色=_线性插值(主题.渐变甲, 主题.渐变乙, 列索引 / _标题宽度))
    刷新输出()
    时间.sleep(0.18)

    显现列: list[int] = list(range(_标题宽度))
    显现模式: str = 随机源.choice(("ltr", "rtl", "center", "random", "wave"))
    match 显现模式:
        case "rtl":
            显现列.reverse()
        case "center":
            中列: int = _标题宽度 // 2
            显现列.sort(key=lambda 颜色值: abs(颜色值 - 中列))
        case "random":
            随机源.shuffle(显现列)
        case "wave":
            显现列.sort(key=lambda 颜色值: 数学.sin(颜色值 * 0.23) * 12 + 颜色值)
        case _:
            ...

    显现批量: int = max(1, _标题宽度 // 24)
    for 块起点 in range(0, len(显现列), 显现批量):
        for 列索引 in 显现列[块起点 : 块起点 + 显现批量]:
            for 序号, 行文本 in enumerate(_标题字形):
                行: int = 标题上边 + 序号
                if 行 > 高度 or 列索引 >= len(行文本):
                    continue
                列: int = 标题左边 + 列索引
                if 1 <= 列 <= 宽度:
                    绘制(行, 列, 行文本[列索引], 颜色=_线性插值(主题.渐变甲, 主题.渐变乙, 列索引 / _标题宽度), 加粗=True)
        刷新输出()
        时间.sleep(0.015)

    副标题文本: str = "✦ 导出我的哔哩哔哩 ✦"
    副标题行: int = 标题上边 + len(_标题字形) + 1
    if 副标题行 <= 高度:
        副标题宽度: int = _中日韩宽度(副标题文本)
        副标题左边: int = max(1, (宽度 - 副标题宽度) // 2)
        当前文本列 = 副标题左边
        for 索引, 字符 in enumerate(副标题文本):
            字符列宽: int = 2 if ord(字符) > 0x7F else 1
            if 字符 != " " and 当前文本列 + 字符列宽 - 1 <= 宽度:
                绘制(副标题行, 当前文本列, 随机源.choice(_闪光字符), 颜色=随机源.choice(主题.辅色组), 加粗=True)
                刷新输出()
                时间.sleep(0.02)
                字符比例: float = 索引 / max(len(副标题文本) - 1, 1)
                绘制(副标题行, 当前文本列, 字符, 颜色=_线性插值(主题.渐变甲, 主题.渐变乙, 字符比例), 加粗=True)
                刷新输出()
                时间.sleep(0.015)
            当前文本列 += 字符列宽

    分隔行: int = 副标题行 + 1 if 副标题行 <= 高度 else 标题上边 + len(_标题字形) + 1
    if 分隔行 <= 高度:
        分隔宽度: int = min(48, 宽度 - 4)
        分隔左边: int = max(1, (宽度 - 分隔宽度) // 2)
        for 序号 in range(分隔宽度):
            绘制(分隔行, 分隔左边 + 序号, 随机源.choice("═━─"), 颜色=_线性插值(主题.渐变甲, 主题.渐变乙, 序号 / 分隔宽度))
        刷新输出()
        时间.sleep(0.08)

    启动提示: str = (
        "  ✦ 服务已就绪, 浏览器即将自动打开"
        if 启动状态 is not None and 启动状态.已启动.is_set()
        else "  ✦ 服务启动中..."
    )

    信息上边: int = 分隔行 + 2
    信息左边: int = max(1, (宽度 - 58) // 2)
    信息行列表: list[tuple[str, tuple[int, int, int]]] = [
        (f"  ✦ 端口   │ {端口}", 主题.辅色组[0]),
        (f"  ✦ 访问   │ http://127.0.0.1:{端口}", 主题.辅色组[1 % len(主题.辅色组)]),
        ("", (0, 0, 0)),
        ("  ✦ 仓库   │ https://github.com/Water-Run/MyBiOut", 主题.渐变甲),
        ("  ✦ 作者   │ WaterRun", 主题.渐变乙),
        ("", (0, 0, 0)),
        (启动提示, _线性插值(主题.渐变甲, 主题.渐变乙, 0.5)),
    ]
    for 索引, (行文本, 颜色) in enumerate(信息行列表):
        行: int = 信息上边 + 索引
        if 行 > 高度 or not 行文本:
            continue
        当前文本列 = 信息左边
        for 字符序号, 字符 in enumerate(行文本):
            if 当前文本列 > 宽度:
                break
            字符列宽: int = 2 if ord(字符) > 0x7F else 1
            绘制(行, 当前文本列, 字符, 颜色=颜色)
            当前文本列 += 字符列宽
            if 字符序号 % 5 == 0:
                刷新输出()
                时间.sleep(0.0045)
        刷新输出()
        时间.sleep(0.02)

    烟花粒子: list[_粒子] = []
    for _ in range(随机源.randint(3, 6)):
        当前列: float = 随机源.uniform(宽度 * 0.15, 宽度 * 0.85)
        当前行: float = 随机源.uniform(2.0, max(3.0, float(标题上边 - 1)))
        _爆发粒子(烟花粒子, 当前列, 当前行, 随机源.randint(15, 32), 主题.辅色组, 速度=7.0, 寿命=(0.3, 1.2), 散布=1.0)

    for _ in range(22):
        烟花粒子 = [粒子 for 粒子 in 烟花粒子 if 粒子.步进(0.05)]
        for 粒子 in 烟花粒子:
            粒子列: int = int(粒子.横坐标)
            粒子行: int = int(粒子.纵坐标)
            if 1 <= 粒子行 <= 高度 and 1 <= 粒子列 <= 宽度:
                绘制(粒子行, 粒子列, 粒子.字符, 颜色=粒子.可见颜色)
        刷新输出()
        时间.sleep(0.03)

    for _ in range(随机源.randint(12, 28)):
        星行: int = 随机源.randint(1, 高度)
        星列: int = 随机源.randint(1, 宽度)
        绘制(星行, 星列, 随机源.choice(_闪光字符), 颜色=随机源.choice(主题.辅色组))
    刷新输出()
    时间.sleep(0.2)

    收尾行: int = min(高度, 信息上边 + len(信息行列表) + 1)
    写入(_定位(收尾行, 1) + _显示光标 + _重置样式)
    刷新输出()


_备用标题: str = r"""
  __  __       ____  _  ___        _   _
 |  \/  |_   _| __ )(_)/ _ \ _   _| |_| |
 | |\/| | | | |  _ \| | | | | | | | __| |
 | |  | | |_| | |_) | | |_| | |_| | |_|_|
 |_|  |_|\__, |____/|_|\___/ \__,_|\__(_)
         |___/                          !
"""


def _可否使用窗口壳() -> bool:
    r"""
    检测 pywebview 是否可用
    :return: bool: 可用返回 True
    """
    try:
        import webview  # noqa: F401

        return True
    except Exception:
        return False


def _停止服务(启动状态: _服务启动状态) -> None:
    r"""
    请求 Uvicorn 退出并等待后台线程结束
    :param 启动状态: 服务启动状态
    """
    if 启动状态.服务 is not None:
        启动状态.服务.should_exit = True
    if 启动状态.线程对象 is not None and 启动状态.线程对象.is_alive():
        启动状态.线程对象.join(timeout=5.0)


def _取窗口图标路径() -> str | None:
    r"""
    窗口/任务栏图标: 优先 logo.ico, 其次 logo.png (包内 assets)
    """
    from pathlib import Path as 路径

    候选根: list[路径] = []
    try:
        from mybiout.pages.utils import 取资源根目录

        候选根.append(取资源根目录())
    except Exception:
        pass
    候选根.append(路径(__file__).resolve().parent)
    for 根 in 候选根:
        for 名 in ("assets/logo.ico", "assets/logo.png"):
            文件 = 根 / 名
            if 文件.is_file():
                return str(文件)
    return None


def _启动窗口壳(端口: int, 启动状态: _服务启动状态) -> None:
    r"""
    使用 pywebview 打开内嵌窗口, 关闭窗口时停止本地服务
    :param 端口: 服务端口
    :param 启动状态: 服务启动状态
    """
    import webview as 网页视图

    地址: str = f"http://127.0.0.1:{端口}/"
    图标 = _取窗口图标路径()

    def _窗口关闭() -> None:
        r"""
        窗口关闭回调: 停止后台服务
        """
        _停止服务(启动状态)

    窗口参数: dict = {
        "title": "MyBiOut!",
        "url": 地址,
        "width": 1280,
        "height": 840,
        "min_size": (960, 640),
        "background_color": "#0b1220",
    }
    if 图标:
        窗口参数["icon"] = 图标
    try:
        窗口 = 网页视图.create_window(**窗口参数)
    except TypeError:
        # 旧版 pywebview 可能不认 icon 参数
        窗口参数.pop("icon", None)
        窗口 = 网页视图.create_window(**窗口参数)
    with 忽略异常(Exception):
        窗口.events.closed += _窗口关闭
    try:
        网页视图.start(debug=False)
    finally:
        _停止服务(启动状态)


def _打印就绪信息(端口: int, *, 使用窗口: bool) -> None:
    r"""
    在控制台打印服务就绪摘要
    使用 * 等 ASCII 符号, 避免 windowed/GBK 下 ✦ 触发 UnicodeEncodeError 整进程崩溃。
    """
    _安全打印(_备用标题)
    _安全打印(f"  * 端口: {端口}")
    _安全打印(f"  * 访问: http://127.0.0.1:{端口}")
    if 使用窗口:
        _安全打印("  * 模式: 绿色内嵌窗口 (关闭窗口即退出)")
    else:
        _安全打印("  * 模式: 系统浏览器")
    _安全打印("  * 仓库: https://github.com/Water-Run/MyBiOut")
    _安全打印("  * 作者: WaterRun")
    _安全打印()


def 主程序() -> None:
    r"""
    程序主入口, 解析命令行并启动 FastAPI 服务
    默认优先使用内嵌 Web 窗口 (绿色套壳); --browser 回退系统浏览器
    :return: None: 无返回值
    """
    _配置文本输出()

    默认端口: int = 取端口()

    解析器: 参数解析.ArgumentParser = _中文参数解析器(
        prog="MyBiOut!",
        description="MyBiOut! 综合性一站式开箱即用哔哩哔哩导出工具集 (绿色版可双击运行)",
    )
    解析器.add_argument(
        "--port",
        type=int,
        default=默认端口,
        help=f"指定服务端口号 (默认: {默认端口})",
    )
    解析器.add_argument(
        "--browser",
        action="store_true",
        help="使用系统浏览器打开界面 (而非内嵌窗口)",
    )
    解析器.add_argument(
        "--no-animation",
        action="store_true",
        help="跳过终端启动动画",
    )
    参数: 参数解析.Namespace = 解析器.parse_args()
    端口: int = 参数.port

    使用窗口: bool = not 参数.browser
    if 使用窗口 and not _可否使用窗口壳():
        使用窗口 = False
        if not 参数.browser:
            _安全打印("  提示: 未安装 pywebview, 已回退为系统浏览器模式")
            _安全打印("        安装: pip install pywebview")
            _安全打印()

    # 冻结绿色包或无可交互终端时跳过动画 (stdout 可能为 None: windowed)
    跳过动画: bool = (
        参数.no_animation
        or 是否冻结运行()
        or 使用窗口
        or not _是否有交互控制台()
    )

    # ===== 环境检查 =====
    环境检查列表: list[_环境项] = _检查环境()
    缺失环境项: list[_环境项] = _取启动阻断项(环境检查列表)

    if 缺失环境项:
        缺失名称: str = ", ".join(检查项.名称 for 检查项 in 缺失环境项)
        启动状态: _服务启动状态 = _服务启动状态()
        启动状态.标记失败(f"缺少必需组件: {缺失名称}")
    else:
        启动状态 = _后台启动服务(端口)

    动画错误: Exception | None = None
    if not 跳过动画:
        try:
            _播放动画(端口, 启动状态)
        except Exception as e:
            动画错误 = e

    if 启动状态.已失败.is_set():
        原因: str = 启动状态.原因 or "未知原因"
        _安全打印(_备用标题)
        _安全打印(f"  * 端口: {端口}")
        _安全打印(f"  * 启动失败: {原因}")
        if 缺失环境项:
            _打印环境详情(环境检查列表)
        else:
            _安全打印("  * 请检查端口占用/配置后重试")
            _安全打印()
        _提示致命错误(f"启动失败: {原因}\n端口: {端口}")
        return

    if 动画错误 is not None and not 使用窗口:
        _打印就绪信息(端口, 使用窗口=False)

    if not _等待服务启动(启动状态, 超时=25.0):
        原因 = 启动状态.原因 or "服务启动超时"
        _安全打印(_备用标题)
        _安全打印(f"  * 端口: {端口}")
        _安全打印(f"  * 启动失败: {原因}")
        _安全打印()
        _提示致命错误(f"启动失败: {原因}\n端口: {端口}")
        return

    if 使用窗口:
        if not 跳过动画:
            _打印就绪信息(端口, 使用窗口=True)
        elif _是否有交互控制台():
            _打印就绪信息(端口, 使用窗口=True)
        try:
            _启动窗口壳(端口, 启动状态)
        except Exception as e:
            _安全打印(f"  * 内嵌窗口启动失败, 回退浏览器: {e}")
            if 是否冻结运行() and not _是否有交互控制台():
                _提示致命错误(
                    f"内嵌窗口启动失败, 将尝试系统浏览器。\n\n{e}\n\n"
                    "若仍无界面, 请安装 WebView2 Runtime 或使用 MyBiOut!.exe --browser"
                )
            使用窗口 = False

    if not 使用窗口:

        def _打开浏览器() -> None:
            r"""
            延迟后自动打开系统浏览器
            """
            时间.sleep(0.35)
            浏览器.open(f"http://127.0.0.1:{端口}")

        if 跳过动画:
            _打印就绪信息(端口, 使用窗口=False)
        线程.Thread(target=_打开浏览器, daemon=True).start()

        try:
            while 启动状态.线程对象 is not None and 启动状态.线程对象.is_alive():
                时间.sleep(0.2)
        except KeyboardInterrupt:
            _停止服务(启动状态)


if __name__ == "__main__":
    try:
        主程序()
    except Exception as 异常:  # noqa: BLE001
        import traceback as 回溯

        详情: str = 回溯.format_exc()
        try:
            from pathlib import Path as _路径

            _根 = _路径(系统.executable).resolve().parent if 是否冻结运行() else _路径.cwd()
            (_根 / "startup_error.log").write_text(详情, encoding="utf-8")
        except Exception:
            pass
        try:
            _提示致命错误(
                f"启动时发生未处理异常:\n\n{异常}\n\n"
                f"详情已写入 startup_error.log（若可写）。\n\n{详情[-1200:]}"
            )
        except Exception:
            pass
        raise
