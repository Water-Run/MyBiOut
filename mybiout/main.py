r"""
MyBiOut! 主入口模块, 解析命令行参数并启动 FastAPI 服务

:file: mybiout/main.py
:author: WaterRun
:time: 2026-03-31
"""

import argparse
import math
import random
import shutil
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass

import uvicorn

from mybiout.pages.utils import get_port

_CSI: str = "\033["
_HIDE_CUR: str = f"{_CSI}?25l"
_SHOW_CUR: str = f"{_CSI}?25h"
_CLR_SCR: str = f"{_CSI}2J{_CSI}H"
_RST: str = f"{_CSI}0m"
_BOLD: str = f"{_CSI}1m"

_BR_L: str = "⠁⠂⠄⡀⠈⠐⠠⢀"
_BR_M: str = "⠃⠅⠆⠉⠊⠌⠑⠒⠔⡁⡂⡄⡈⡐⡠⢁⢂⢄⢈⢐⢠⣀"
_BR_H: str = "⠿⡿⢿⣿⣾⣽⣻⣷⣯⣟⡷⡯⡟⠷⠯⠟⣶⣵⣳"
_SPARK: str = "✦✧⋆˚✩✫✬✮✰⊹✵✺❖"
_MAX_PARTICLES: int = 280


def _at(row: int, col: int) -> str:
    r"""
    生成终端光标定位控制序列

    :param row: 行号, 1-based
    :param col: 列号, 1-based
    :return: str: ANSI 控制序列
    """
    return f"{_CSI}{row};{col}H"


def _fg(r: int, g: int, b: int) -> str:
    r"""
    生成 24-bit 真彩前景色 ANSI 控制序列

    :param r: 红色分量
    :param g: 绿色分量
    :param b: 蓝色分量
    :return: str: ANSI 控制序列
    """
    return f"{_CSI}38;2;{r};{g};{b}m"


def _lerp(
    a: tuple[int, int, int],
    b: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    r"""
    对 RGB 颜色做线性插值

    :param a: 起始颜色
    :param b: 结束颜色
    :param t: 插值比例, 自动钳制到 [0.0, 1.0]
    :return: tuple[int, int, int]: 插值后的颜色
    """
    t_clamped: float = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t_clamped),
        int(a[1] + (b[1] - a[1]) * t_clamped),
        int(a[2] + (b[2] - a[2]) * t_clamped),
    )


def _fade(c: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    r"""
    将颜色按比例淡化到黑色

    :param c: 原始颜色
    :param alpha: 强度比例, 自动钳制到 [0.0, 1.0]
    :return: tuple[int, int, int]: 淡化后的颜色
    """
    a: float = max(0.0, min(1.0, alpha))
    return int(c[0] * a), int(c[1] * a), int(c[2] * a)


def _cjk_len(text: str) -> int:
    r"""
    估算字符串在终端中的显示宽度, CJK 字符按 2 列计

    :param text: 输入文本
    :return: int: 显示宽度
    """
    return sum(
        2
        if (
            0x2E80 <= ord(ch) <= 0x9FFF
            or 0xF900 <= ord(ch) <= 0xFAFF
            or 0xFF00 <= ord(ch) <= 0xFF60
            or 0x20000 <= ord(ch) <= 0x2FA1F
        )
        else 1
        for ch in text
    )


@dataclass(frozen=True, slots=True)
class _Theme:
    r"""
    动画配色主题
    """

    ga: tuple[int, int, int]
    gb: tuple[int, int, int]
    acc: tuple[tuple[int, int, int], ...]
    heli: tuple[int, int, int]
    stars: tuple[tuple[int, int, int], ...]


_THEMES: tuple[_Theme, ...] = (
    _Theme((0, 255, 255), (255, 0, 255), ((255, 255, 0), (0, 255, 200), (255, 100, 255)), (0, 255, 220), ((60, 60, 100), (80, 50, 120), (50, 70, 110))),
    _Theme((255, 220, 50), (255, 30, 0), ((255, 255, 120), (255, 180, 50), (255, 100, 20)), (255, 210, 70), ((100, 60, 30), (120, 80, 20), (80, 50, 25))),
    _Theme((0, 255, 128), (100, 0, 255), ((200, 255, 200), (160, 220, 255), (180, 100, 255)), (0, 255, 190), ((30, 80, 60), (40, 60, 100), (50, 50, 90))),
    _Theme((251, 114, 153), (0, 174, 236), ((255, 200, 220), (120, 215, 255), (255, 160, 190)), (251, 114, 153), ((80, 40, 55), (30, 60, 90), (60, 45, 70))),
    _Theme((0, 210, 120), (255, 215, 0), ((200, 255, 160), (255, 240, 120), (80, 255, 180)), (0, 230, 130), ((30, 80, 40), (60, 70, 20), (40, 90, 50))),
    _Theme((0, 80, 255), (0, 255, 200), ((100, 200, 255), (0, 255, 190), (80, 140, 255)), (0, 180, 255), ((15, 30, 70), (20, 40, 80), (10, 25, 60))),
    _Theme((255, 183, 197), (255, 105, 180), ((255, 228, 225), (255, 182, 193), (255, 240, 245)), (255, 150, 170), ((90, 50, 60), (80, 40, 55), (100, 60, 70))),
    _Theme((255, 215, 0), (180, 130, 50), ((255, 240, 150), (220, 190, 80), (255, 200, 60)), (255, 220, 100), ((50, 40, 20), (60, 50, 25), (40, 35, 18))),
    _Theme((148, 0, 211), (75, 0, 130), ((238, 130, 238), (186, 85, 211), (147, 112, 219)), (199, 21, 133), ((70, 30, 90), (60, 20, 80), (50, 20, 70))),
    _Theme((0, 191, 255), (30, 144, 255), ((176, 224, 230), (135, 206, 250), (173, 216, 230)), (70, 130, 180), ((40, 70, 90), (30, 60, 80), (20, 50, 70))),
    _Theme((50, 205, 50), (124, 252, 0), ((152, 251, 152), (144, 238, 144), (173, 255, 47)), (34, 139, 34), ((30, 70, 30), (20, 60, 20), (10, 50, 10))),
    _Theme((255, 140, 0), (255, 69, 0), ((255, 218, 185), (255, 160, 122), (255, 127, 80)), (255, 165, 0), ((90, 50, 20), (80, 40, 20), (70, 35, 15))),
    _Theme((173, 216, 230), (230, 230, 250), ((240, 248, 255), (224, 255, 255), (245, 245, 255)), (176, 196, 222), ((60, 70, 90), (50, 60, 80), (45, 55, 75))),
    _Theme((64, 224, 208), (138, 43, 226), ((173, 255, 240), (120, 180, 255), (210, 140, 255)), (102, 255, 224), ((20, 50, 70), (40, 30, 80), (25, 60, 85))),
    _Theme((0, 255, 170), (255, 0, 140), ((0, 255, 255), (255, 80, 220), (255, 240, 0)), (0, 255, 200), ((25, 35, 70), (45, 20, 60), (20, 45, 55))),
    _Theme((0, 120, 180), (0, 255, 140), ((100, 220, 255), (80, 255, 200), (180, 255, 240)), (0, 200, 170), ((10, 35, 55), (15, 45, 65), (8, 30, 48))),
    _Theme((255, 80, 0), (120, 0, 40), ((255, 170, 80), (255, 110, 60), (220, 40, 80)), (255, 120, 40), ((70, 25, 18), (55, 18, 22), (80, 30, 15))),
    _Theme((170, 255, 220), (255, 245, 200), ((210, 255, 230), (255, 255, 225), (190, 245, 220)), (170, 240, 210), ((45, 65, 55), (60, 70, 50), (50, 60, 52))),
    _Theme((170, 120, 255), (255, 140, 220), ((220, 190, 255), (255, 180, 240), (190, 160, 255)), (210, 140, 255), ((45, 35, 80), (65, 40, 75), (55, 30, 70))),
    _Theme((70, 170, 90), (180, 220, 140), ((140, 220, 150), (200, 240, 170), (100, 190, 120)), (90, 190, 110), ((25, 55, 30), (35, 60, 28), (22, 48, 24))),
    _Theme((120, 200, 255), (220, 245, 255), ((170, 225, 255), (200, 240, 255), (235, 250, 255)), (150, 210, 255), ((30, 45, 70), (40, 55, 75), (28, 40, 60))),
    _Theme((255, 140, 90), (255, 210, 120), ((255, 185, 140), (255, 225, 160), (255, 155, 120)), (255, 175, 110), ((70, 40, 28), (80, 50, 30), (65, 35, 24))),
    _Theme((65, 105, 225), (255, 215, 120), ((120, 150, 255), (255, 235, 170), (170, 200, 255)), (120, 150, 245), ((25, 35, 70), (45, 40, 55), (20, 30, 60))),
    _Theme((255, 130, 180), (120, 60, 170), ((255, 180, 215), (180, 130, 220), (255, 150, 200)), (230, 120, 190), ((60, 35, 60), (45, 30, 75), (70, 40, 68))),
    _Theme((210, 170, 110), (140, 110, 70), ((235, 205, 150), (200, 160, 110), (170, 135, 90)), (220, 180, 120), ((60, 45, 28), (55, 40, 25), (48, 35, 22))),
    _Theme((90, 120, 170), (180, 220, 255), ((140, 170, 220), (200, 230, 255), (120, 150, 210)), (130, 170, 230), ((20, 28, 50), (28, 35, 60), (18, 24, 45))),
    _Theme((80, 190, 130), (30, 120, 90), ((130, 220, 160), (90, 180, 130), (160, 240, 190)), (70, 180, 120), ((18, 45, 32), (20, 55, 38), (15, 38, 28))),
    _Theme((255, 180, 60), (140, 70, 220), ((255, 220, 120), (190, 130, 255), (255, 190, 90)), (240, 170, 80), ((45, 35, 60), (60, 35, 75), (50, 30, 65))),
    _Theme((255, 127, 120), (80, 220, 220), ((255, 170, 160), (130, 240, 235), (255, 205, 180)), (130, 225, 220), ((55, 35, 42), (25, 60, 65), (45, 45, 55))),
    _Theme((140, 160, 190), (255, 190, 120), ((180, 200, 220), (255, 215, 150), (160, 180, 210)), (180, 200, 230), ((35, 40, 52), (55, 48, 40), (30, 35, 48))),
    _Theme((255, 170, 200), (255, 220, 245), ((255, 195, 220), (255, 235, 250), (245, 210, 235)), (255, 185, 210), ((70, 40, 60), (80, 50, 70), (65, 38, 55))),
    _Theme((170, 255, 0), (0, 200, 140), ((210, 255, 90), (90, 240, 180), (235, 255, 130)), (140, 240, 80), ((35, 55, 18), (15, 60, 40), (25, 45, 20))),
    _Theme((70, 90, 110), (220, 180, 90), ((120, 150, 180), (240, 210, 130), (170, 140, 95)), (200, 170, 100), ((18, 22, 30), (30, 28, 22), (22, 24, 20))),
    _Theme((110, 140, 180), (190, 200, 210), ((160, 185, 215), (200, 210, 225), (140, 160, 195)), (150, 175, 210), ((28, 35, 50), (35, 42, 58), (22, 30, 45))),
    _Theme((220, 30, 50), (150, 10, 30), ((255, 100, 110), (240, 70, 80), (200, 50, 60)), (240, 60, 70), ((75, 15, 20), (60, 10, 18), (85, 20, 25))),
    _Theme((130, 225, 200), (80, 200, 170), ((180, 245, 225), (140, 230, 210), (200, 250, 235)), (110, 220, 195), ((25, 55, 48), (20, 50, 42), (30, 60, 52))),
    _Theme((220, 160, 50), (180, 110, 30), ((245, 200, 100), (230, 170, 70), (200, 140, 50)), (230, 175, 60), ((65, 45, 18), (55, 38, 15), (70, 50, 22))),
    _Theme((80, 70, 160), (110, 100, 180), ((140, 135, 210), (120, 115, 195), (160, 155, 225)), (100, 90, 190), ((22, 20, 55), (28, 25, 60), (18, 16, 48))),
    _Theme((255, 110, 100), (255, 160, 130), ((255, 175, 155), (255, 195, 170), (255, 145, 125)), (255, 135, 115), ((72, 32, 28), (65, 38, 35), (80, 35, 30))),
    _Theme((180, 130, 160), (140, 90, 120), ((210, 170, 195), (195, 150, 175), (225, 190, 210)), (190, 145, 175), ((50, 35, 45), (42, 28, 38), (55, 40, 50))),
    _Theme((180, 240, 50), (40, 140, 100), ((215, 250, 110), (100, 220, 160), (230, 255, 140)), (160, 235, 70), ((38, 60, 20), (18, 50, 35), (30, 55, 22))),
    _Theme((190, 110, 70), (150, 75, 45), ((225, 155, 110), (210, 135, 90), (200, 120, 80)), (205, 125, 80), ((58, 30, 20), (50, 25, 16), (65, 35, 22))),
    _Theme((180, 220, 250), (200, 235, 255), ((210, 235, 255), (195, 228, 250), (225, 242, 255)), (190, 225, 250), ((35, 50, 68), (42, 58, 75), (30, 45, 62))),
    _Theme((160, 60, 120), (120, 30, 80), ((200, 100, 160), (180, 80, 140), (170, 70, 130)), (180, 70, 140), ((48, 18, 38), (40, 12, 30), (55, 22, 42))),
    _Theme((140, 160, 100), (110, 130, 70), ((180, 195, 140), (165, 180, 120), (155, 170, 110)), (150, 170, 110), ((35, 42, 25), (30, 38, 20), (40, 45, 28))),
    _Theme((255, 180, 140), (240, 130, 80), ((255, 210, 175), (255, 195, 155), (250, 170, 130)), (255, 190, 150), ((68, 42, 30), (60, 38, 28), (75, 48, 35))),
    _Theme((30, 40, 100), (50, 60, 140), ((80, 95, 170), (65, 80, 155), (100, 110, 185)), (60, 75, 160), ((10, 14, 38), (15, 18, 45), (8, 12, 32))),
    _Theme((180, 220, 50), (80, 140, 30), ((210, 240, 100), (140, 200, 80), (225, 245, 120)), (160, 210, 60), ((40, 55, 15), (25, 48, 12), (45, 58, 18))),
    _Theme((230, 140, 120), (180, 100, 80), ((245, 180, 160), (240, 165, 145), (220, 150, 130)), (235, 155, 135), ((62, 38, 32), (55, 32, 25), (68, 42, 35))),
    _Theme((0, 180, 180), (220, 50, 160), ((80, 220, 220), (240, 120, 200), (140, 255, 240)), (0, 210, 200), ((15, 48, 50), (55, 20, 45), (20, 55, 58))),
)

_ROTORS: tuple[str, ...] = (
    "      ----|----       ",
    "      \\---|---/       ",
    "      --\\-|-/--       ",
    "      /---|---\\       ",
)
_BODY: tuple[str, ...] = (
    "         __|__         ",
    "   ____ /[_] \\____     ",
    "--=|____  _  ____|===> ",
    "       /_/ \\_\\         ",
    "       O     O         ",
)
_HELI_W: int = max(*(len(s) for s in _ROTORS), *(len(s) for s in _BODY))
_HELI_H: int = 1 + len(_BODY)

_TITLE: tuple[str, ...] = (
    r"  __  __       ____  _  ___        _   _ ",
    r" |  \/  |_   _| __ )(_)/ _ \ _   _| |_| |",
    r" | |\/| | | | |  _ \| | | | | | | | __| |",
    r" | |  | | |_| | |_) | | |_| | |_| | |_|_|",
    r" |_|  |_|\__, |____/|_|\___/ \__,_|\__(_)",
    r"         |___/                          ! ",
)
_TITLE_W: int = max(len(s) for s in _TITLE)


@dataclass(slots=True)
class _Particle:
    r"""
    粒子对象, 用于盲文特效
    """

    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: tuple[int, int, int]

    def step(self, dt: float) -> bool:
        r"""
        推进粒子物理状态

        :param dt: 时间步长
        :return: bool: 是否仍存活
        """
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 3.5 * dt
        self.life -= dt
        return self.life > 0

    @property
    def ch(self) -> str:
        r"""
        获取当前寿命对应的盲文字符密度

        :return: str: 单字符
        """
        ratio: float = self.life / self.max_life if self.max_life > 0 else 0.0
        if ratio > 0.6:
            return random.choice(_BR_H)
        if ratio > 0.25:
            return random.choice(_BR_M)
        return random.choice(_BR_L)

    @property
    def visible_color(self) -> tuple[int, int, int]:
        r"""
        获取当前可见颜色

        :return: tuple[int, int, int]: RGB 颜色
        """
        ratio: float = self.life / self.max_life if self.max_life > 0 else 0.0
        return _fade(self.color, ratio)


def _burst(
    pool: list[_Particle],
    x: float,
    y: float,
    count: int,
    colors: tuple[tuple[int, int, int], ...],
    *,
    speed: float = 5.0,
    life: tuple[float, float] = (0.4, 1.2),
    spread: float = 1.0,
) -> None:
    r"""
    在指定位置生成爆发粒子

    :param pool: 粒子池
    :param x: 爆发中心 x
    :param y: 爆发中心 y
    :param count: 粒子数量
    :param colors: 颜色集合
    :param speed: 初速度上限
    :param life: 生命周期范围
    :param spread: 初始位置离散半径
    :return: None: 无返回值
    """
    for _ in range(count):
        angle: float = random.uniform(0.0, math.tau)
        v_abs: float = random.uniform(speed * 0.3, speed)
        ttl: float = random.uniform(*life)
        pool.append(
            _Particle(
                x=x + random.uniform(-spread, spread),
                y=y + random.uniform(-spread * 0.3, spread * 0.3),
                vx=math.cos(angle) * v_abs,
                vy=math.sin(angle) * v_abs * 0.4,
                life=ttl,
                max_life=ttl,
                color=random.choice(colors),
            ),
        )
    if len(pool) > _MAX_PARTICLES:
        del pool[: len(pool) - _MAX_PARTICLES]


def _play_animation(port: int) -> None:
    r"""
    播放启动动画序列

    :param port: 服务端口号
    :return: None: 无返回值
    :raise RuntimeError: 终端尺寸过小时抛出
    """
    width, height = shutil.get_terminal_size((80, 24))
    if width < 52 or height < 18:
        raise RuntimeError("终端尺寸过小, 跳过动画")

    theme: _Theme = random.choice(_THEMES)
    rng: random.Random = random.Random()
    buffer: list[str] = []

    def w(text: str) -> None:
        r"""
        向输出缓冲写入字符串

        :param text: 输出文本
        :return: None: 无返回值
        """
        buffer.append(text)

    def flush() -> None:
        r"""
        刷新输出缓冲到终端

        :return: None: 无返回值
        """
        sys.stdout.write("".join(buffer))
        sys.stdout.flush()
        buffer.clear()

    def put(
        row: int,
        col: int,
        text: str,
        color: tuple[int, int, int] | None = None,
        bold: bool = False,
    ) -> None:
        r"""
        在终端指定位置绘制文本

        :param row: 行号, 1-based
        :param col: 列号, 1-based
        :param text: 输出文本
        :param color: RGB 颜色
        :param bold: 是否加粗
        :return: None: 无返回值
        """
        if row < 1 or row > height or col > width:
            return
        clipped: str = text[: width - col + 1]
        if not clipped:
            return
        payload: str = _at(row, col)
        if bold:
            payload += _BOLD
        if color is not None:
            payload += _fg(*color)
        w(payload + clipped + _RST)

    def clear_row(row: int, c1: int = 1, c2: int | None = None) -> None:
        r"""
        清空指定行区间

        :param row: 行号
        :param c1: 起始列
        :param c2: 结束列, 为空时到行尾
        :return: None: 无返回值
        """
        if row < 1 or row > height:
            return
        end_col: int = min(c2 or width, width)
        length: int = end_col - c1 + 1
        if length > 0:
            w(_at(row, max(1, c1)) + " " * length)

    w(_HIDE_CUR + _CLR_SCR)
    flush()

    star_count: int = rng.randint(width * height // 35, width * height // 16)
    stars: list[tuple[int, int, str, tuple[int, int, int]]] = [
        (
            rng.randint(1, height),
            rng.randint(1, width),
            rng.choice(_BR_L + "·.˙"),
            rng.choice(theme.stars),
        )
        for _ in range(star_count)
    ]
    rng.shuffle(stars)
    batch: int = max(1, len(stars) // 8)
    for idx in range(0, len(stars), batch):
        for sr, sc, sch, sco in stars[idx : idx + batch]:
            put(sr, sc, sch, color=sco)
        flush()
        time.sleep(0.02)

    base_y: int = max(3, height // 4)
    wave_amp: float = rng.uniform(0.3, 1.8)
    wave_freq: float = rng.uniform(1.0, 3.0)
    frame_count: int = 58 + rng.randint(-8, 10)
    dt: float = 0.032
    particles: list[_Particle] = []
    prev_r: int = base_y
    prev_c: int = width + 6
    bili_row: int = min(base_y + _HELI_H + 2, height - 2)
    bili_burst_done: bool = False

    for frame in range(frame_count):
        t: float = frame / frame_count
        heli_x: int = int((width + 6) + ((-_HELI_W - 6) - (width + 6)) * t)
        heli_y: int = int(base_y + wave_amp * math.sin(wave_freq * t * math.tau))

        for dr in range(_HELI_H):
            clear_row(prev_r + dr, max(1, prev_c), min(width, prev_c + _HELI_W + 2))

        particles = [p for p in particles if p.step(dt)]
        for p in particles:
            px: int = int(p.x)
            py: int = int(p.y)
            if 1 <= py <= height and 1 <= px <= width:
                put(py, px, p.ch, color=p.visible_color)

        exhaust_x: float = float(heli_x + _HELI_W - 2)
        exhaust_y: float = float(heli_y + 3)
        for _ in range(rng.randint(4, 9)):
            ttl: float = rng.uniform(0.3, 1.1)
            particles.append(
                _Particle(
                    x=exhaust_x + rng.uniform(0.0, 2.4),
                    y=exhaust_y + rng.uniform(-0.6, 0.6),
                    vx=rng.uniform(1.2, 6.5),
                    vy=rng.uniform(-1.0, 1.0),
                    life=ttl,
                    max_life=ttl,
                    color=rng.choice(theme.acc),
                ),
            )
        if len(particles) > _MAX_PARTICLES:
            del particles[: len(particles) - _MAX_PARTICLES]

        rotor: str = _ROTORS[frame % len(_ROTORS)]
        for ci, ch in enumerate(rotor):
            col: int = heli_x + ci
            if 1 <= col <= width and 1 <= heli_y <= height and ch != " ":
                put(heli_y, col, ch, color=theme.heli, bold=True)

        for bi, line in enumerate(_BODY):
            row: int = heli_y + 1 + bi
            for ci, ch in enumerate(line):
                col: int = heli_x + ci
                if 1 <= col <= width and 1 <= row <= height and ch != " ":
                    put(row, col, ch, color=theme.heli, bold=True)

        if not bili_burst_done and abs(heli_x + _HELI_W // 2 - width // 2) < 8:
            bili_burst_done = True
            _burst(
                particles,
                width / 2,
                bili_row,
                42,
                theme.acc,
                speed=9.0,
                life=(0.5, 2.0),
                spread=5.0,
            )

        prev_r, prev_c = heli_y, heli_x
        flush()
        time.sleep(dt)

    for _ in range(16):
        particles = [p for p in particles if p.step(0.06)]
        for p in particles:
            px: int = int(p.x)
            py: int = int(p.y)
            if 1 <= py <= height and 1 <= px <= width:
                put(py, px, p.ch, color=p.visible_color)
        flush()
        time.sleep(0.032)

    bili_text: str = "哔 哩 哔 哩"
    if 1 <= bili_row <= height:
        text_width: int = _cjk_len(bili_text)
        start_col: int = max(1, (width - text_width) // 2)
        cur_col: int = start_col
        for ch in bili_text:
            ch_width: int = 2 if ord(ch) > 0x7F else 1
            if ch != " " and cur_col + ch_width - 1 <= width:
                for _ in range(3):
                    put(bili_row, cur_col, rng.choice(_BR_H), color=rng.choice(theme.acc), bold=True)
                    flush()
                    time.sleep(0.016)
                put(bili_row, cur_col, ch, color=rng.choice(theme.acc), bold=True)
                flush()
                time.sleep(0.035)
            cur_col += ch_width

    time.sleep(0.24)

    wipe_mode: str = rng.choice(("down", "up", "center", "split"))
    row_order: list[int] = list(range(1, height + 1))
    match wipe_mode:
        case "up":
            row_order.reverse()
        case "center":
            middle: int = height // 2
            row_order.sort(key=lambda r: abs(r - middle))
        case "split":
            top: list[int] = list(range(1, height // 2 + 1))
            bottom: list[int] = list(range(height, height // 2, -1))
            row_order = [r for pair in zip(top, bottom) for r in pair]
            row_order += top[len(bottom) :] or bottom[len(top) :]
        case _:
            ...

    for row in row_order:
        line: str = "".join(rng.choice(_BR_M) for _ in range(width))
        put(row, 1, line, color=_lerp(theme.ga, theme.gb, row / height))
        if row % 2 == 0:
            flush()
            time.sleep(0.005)
    flush()
    time.sleep(0.06)

    for row in row_order:
        clear_row(row)
        if row % 3 == 0:
            flush()
            time.sleep(0.0025)
    flush()

    title_top: int = max(2, height // 2 - len(_TITLE) // 2 - 4)
    title_left: int = max(1, (width - _TITLE_W) // 2)

    for i, line in enumerate(_TITLE):
        row: int = title_top + i
        if row > height:
            break
        for ci, ch in enumerate(line):
            col: int = title_left + ci
            if ch != " " and 1 <= col <= width:
                put(row, col, rng.choice(_BR_H), color=_lerp(theme.ga, theme.gb, ci / _TITLE_W))
    flush()
    time.sleep(0.18)

    reveal_cols: list[int] = list(range(_TITLE_W))
    reveal_mode: str = rng.choice(("ltr", "rtl", "center", "random", "wave"))
    match reveal_mode:
        case "rtl":
            reveal_cols.reverse()
        case "center":
            mid: int = _TITLE_W // 2
            reveal_cols.sort(key=lambda c: abs(c - mid))
        case "random":
            rng.shuffle(reveal_cols)
        case "wave":
            reveal_cols.sort(key=lambda c: math.sin(c * 0.23) * 12 + c)
        case _:
            ...

    batch_reveal: int = max(1, _TITLE_W // 24)
    for block_start in range(0, len(reveal_cols), batch_reveal):
        for ci in reveal_cols[block_start : block_start + batch_reveal]:
            for i, line in enumerate(_TITLE):
                row: int = title_top + i
                if row > height or ci >= len(line):
                    continue
                col: int = title_left + ci
                if 1 <= col <= width:
                    put(row, col, line[ci], color=_lerp(theme.ga, theme.gb, ci / _TITLE_W), bold=True)
        flush()
        time.sleep(0.015)

    sub_text: str = "✦ 导出我的哔哩哔哩 ✦"
    sub_row: int = title_top + len(_TITLE) + 1
    if sub_row <= height:
        sub_w: int = _cjk_len(sub_text)
        sub_left: int = max(1, (width - sub_w) // 2)
        cur_col = sub_left
        for idx, ch in enumerate(sub_text):
            ch_w: int = 2 if ord(ch) > 0x7F else 1
            if ch != " " and cur_col + ch_w - 1 <= width:
                put(sub_row, cur_col, rng.choice(_SPARK), color=rng.choice(theme.acc), bold=True)
                flush()
                time.sleep(0.02)
                t_ratio: float = idx / max(len(sub_text) - 1, 1)
                put(sub_row, cur_col, ch, color=_lerp(theme.ga, theme.gb, t_ratio), bold=True)
                flush()
                time.sleep(0.015)
            cur_col += ch_w

    sep_row: int = sub_row + 1 if sub_row <= height else title_top + len(_TITLE) + 1
    if sep_row <= height:
        sep_w: int = min(48, width - 4)
        sep_left: int = max(1, (width - sep_w) // 2)
        for i in range(sep_w):
            put(sep_row, sep_left + i, rng.choice("═━─"), color=_lerp(theme.ga, theme.gb, i / sep_w))
        flush()
        time.sleep(0.08)

    info_top: int = sep_row + 2
    info_left: int = max(1, (width - 58) // 2)
    info_lines: list[tuple[str, tuple[int, int, int]]] = [
        (f"  ✦ 端口   │ {port}", theme.acc[0]),
        (f"  ✦ 访问   │ http://localhost:{port}", theme.acc[1 % len(theme.acc)]),
        ("", (0, 0, 0)),
        ("  ✦ GitHub │ https://github.com/Water-Run/MyBiOut", theme.ga),
        ("  ✦ Author │ WaterRun", theme.gb),
        ("", (0, 0, 0)),
        ("  ✦ 服务已就绪, 浏览器即将自动打开", _lerp(theme.ga, theme.gb, 0.5)),
    ]
    for idx, (line, color) in enumerate(info_lines):
        row: int = info_top + idx
        if row > height or not line:
            continue
        cur_col = info_left
        for char_idx, ch in enumerate(line):
            if cur_col > width:
                break
            ch_w: int = 2 if ord(ch) > 0x7F else 1
            put(row, cur_col, ch, color=color)
            cur_col += ch_w
            if char_idx % 5 == 0:
                flush()
                time.sleep(0.0045)
        flush()
        time.sleep(0.02)

    fireworks: list[_Particle] = []
    for _ in range(rng.randint(3, 6)):
        cx: float = rng.uniform(width * 0.15, width * 0.85)
        cy: float = rng.uniform(2.0, max(3.0, float(title_top - 1)))
        _burst(fireworks, cx, cy, rng.randint(15, 32), theme.acc, speed=7.0, life=(0.3, 1.2), spread=1.0)

    for _ in range(22):
        fireworks = [p for p in fireworks if p.step(0.05)]
        for p in fireworks:
            px: int = int(p.x)
            py: int = int(p.y)
            if 1 <= py <= height and 1 <= px <= width:
                put(py, px, p.ch, color=p.visible_color)
        flush()
        time.sleep(0.03)

    for _ in range(rng.randint(12, 28)):
        sr: int = rng.randint(1, height)
        sc: int = rng.randint(1, width)
        put(sr, sc, rng.choice(_SPARK), color=rng.choice(theme.acc))
    flush()
    time.sleep(0.2)

    final_row: int = min(height, info_top + len(info_lines) + 1)
    w(_at(final_row, 1) + _SHOW_CUR + _RST)
    flush()


_BANNER_FALLBACK: str = r"""
  __  __       ____  _  ___        _   _
 |  \/  |_   _| __ )(_)/ _ \ _   _| |_| |
 | |\/| | | | |  _ \| | | | | | | | __| |
 | |  | | |_| | |_) | | |_| | |_| | |_|_|
 |_|  |_|\__, |____/|_|\___/ \__,_|\__(_)
         |___/                          !
"""


def main() -> None:
    r"""
    程序主入口, 解析命令行并启动 FastAPI 服务

    :return: None: 无返回值
    """
    default_port: int = get_port()

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog="MyBiOut!",
        description="MyBiOut! 综合性一站式开箱即用哔哩哔哩导出工具集",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help=f"指定服务端口号 (默认: {default_port})",
    )
    args: argparse.Namespace = parser.parse_args()
    port: int = args.port

    try:
        _play_animation(port)
    except Exception:
        print(_BANNER_FALLBACK)
        print(f"  ✦ 端口: {port}")
        print(f"  ✦ 访问: http://localhost:{port}")
        print("  ✦ GitHub: https://github.com/Water-Run/MyBiOut")
        print("  ✦ Author: WaterRun")
        print()

    def _open_browser() -> None:
        r"""
        延迟后自动打开浏览器访问地址

        :return: None: 无返回值
        """
        time.sleep(1.5)
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(
        "mybiout.pages.apis:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()