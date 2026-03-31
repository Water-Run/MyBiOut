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
import socket
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field

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


@dataclass(slots=True)
class _ServerStartupState:
    r"""
    Uvicorn 后台启动状态
    """

    started: threading.Event = field(default_factory=threading.Event)
    failed: threading.Event = field(default_factory=threading.Event)
    reason: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)
    server: uvicorn.Server | None = None
    thread: threading.Thread | None = None

    def mark_started(self) -> None:
        r"""
        标记服务已启动
        """
        with self.lock:
            if self.failed.is_set():
                return
            self.started.set()

    def mark_failed(self, reason: str) -> None:
        r"""
        标记服务启动失败
        :param reason: 失败原因
        """
        with self.lock:
            if self.started.is_set() or self.failed.is_set():
                return
            self.reason = reason
            self.failed.set()


def _probe_port_bind_error(port: int) -> str | None:
    r"""
    预探测端口是否可绑定
    :param port: 端口号
    :return: str | None: 可用返回 None，不可用返回错误原因
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", port))
    except OSError as e:
        detail: str = e.strerror or str(e)
        return f"端口 {port} 不可用: {detail}"
    return None


def _start_server_in_background(port: int) -> _ServerStartupState:
    r"""
    后台启动 Uvicorn，并异步监控启动结果
    :param port: 服务端口号
    :return: _ServerStartupState: 启动状态对象
    """
    state: _ServerStartupState = _ServerStartupState()

    if err := _probe_port_bind_error(port):
        state.mark_failed(err)
        return state

    config: uvicorn.Config = uvicorn.Config(
        "mybiout.pages.apis:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server: uvicorn.Server = uvicorn.Server(config)
    state.server = server

    def _run() -> None:
        r"""
        后台线程执行 server.run()
        """
        try:
            server.run()
        except Exception as e:
            state.mark_failed(f"Uvicorn 启动异常: {e}")

    t: threading.Thread = threading.Thread(target=_run, daemon=True)
    state.thread = t
    t.start()

    def _watch_startup() -> None:
        r"""
        监控 server.started 与线程生命周期，判定启动成功/失败
        """
        deadline: float = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if state.failed.is_set():
                return
            if server.started:
                state.mark_started()
                return
            if not t.is_alive():
                state.mark_failed("服务线程提前退出（可能端口占用或应用初始化失败）")
                return
            time.sleep(0.03)

        if server.started:
            state.mark_started()
            return

        state.mark_failed("服务启动超时")
        server.should_exit = True

    threading.Thread(target=_watch_startup, daemon=True).start()
    return state


def _wait_server_startup(state: _ServerStartupState, timeout: float = 25.0) -> bool:
    r"""
    等待服务启动成功或失败
    :param state: 启动状态对象
    :param timeout: 最大等待秒数
    :return: bool: True=成功, False=失败或超时
    """
    deadline: float = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if state.started.is_set():
            return True
        if state.failed.is_set():
            return False
        time.sleep(0.05)
    return state.started.is_set()


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


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
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


def _play_animation(port: int, startup_state: _ServerStartupState | None = None) -> None:
    r"""
    播放启动动画序列
    :param port: 服务端口号
    :param startup_state: 服务启动状态对象（可选）
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
        """
        buffer.append(text)

    def flush() -> None:
        r"""
        刷新输出缓冲到终端
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

    def _crash_sequence(heli_x: int, heli_y: int, reason: str) -> None:
        r"""
        启动失败时的坠机动画
        :param heli_x: 当前直升机 x
        :param heli_y: 当前直升机 y
        :param reason: 失败原因
        """
        crash_colors: tuple[tuple[int, int, int], ...] = ((255, 200, 80), (255, 120, 60), (255, 70, 70))
        cx: int = heli_x
        cy: int = heli_y
        local_prev_r: int = heli_y
        local_prev_c: int = heli_x

        for step in range(18):
            for dr in range(_HELI_H):
                clear_row(local_prev_r + dr, max(1, local_prev_c), min(width, local_prev_c + _HELI_W + 3))

            cx = min(width - _HELI_W, cx + 1 + (1 if step > 10 else 0))
            cy = min(height - _HELI_H - 1, cy + 1)

            _burst(
                particles,
                cx + _HELI_W * 0.45,
                cy + _HELI_H * 0.75,
                10 + step // 2,
                crash_colors,
                speed=8.0,
                life=(0.25, 0.9),
                spread=1.5,
            )

            particles[:] = [p for p in particles if p.step(0.045)]
            for p in particles:
                px: int = int(p.x)
                py: int = int(p.y)
                if 1 <= py <= height and 1 <= px <= width:
                    put(py, px, p.ch, color=p.visible_color)

            rotor: str = _ROTORS[step % len(_ROTORS)]
            for ci, ch in enumerate(rotor):
                col: int = cx + ci
                if ch != " ":
                    put(cy, col, ch, color=(255, 120, 80), bold=True)

            for bi, line in enumerate(_BODY):
                row: int = cy + 1 + bi
                for ci, ch in enumerate(line):
                    col: int = cx + ci
                    if ch != " ":
                        put(row, col, ch, color=(255, 90, 90), bold=True)

            local_prev_r, local_prev_c = cy, cx
            flush()
            time.sleep(0.03)

        _burst(
            particles,
            cx + _HELI_W * 0.5,
            cy + _HELI_H * 0.8,
            85,
            ((255, 230, 120), (255, 150, 80), (255, 80, 80)),
            speed=10.0,
            life=(0.3, 1.3),
            spread=2.5,
        )

        for _ in range(22):
            particles[:] = [p for p in particles if p.step(0.05)]
            for p in particles:
                px: int = int(p.x)
                py: int = int(p.y)
                if 1 <= py <= height and 1 <= px <= width:
                    put(py, px, p.ch, color=p.visible_color)
            flush()
            time.sleep(0.025)

        title: str = "✖ 服务启动失败，坠机"
        reason_line: str = f"原因: {reason or '未知错误'}"
        if len(reason_line) > max(12, width - 4):
            reason_line = reason_line[: max(9, width - 7)] + "..."

        tr: int = max(2, height // 2 - 1)
        clear_row(tr, 1, width)
        clear_row(tr + 1, 1, width)
        put(tr, max(1, (width - len(title)) // 2), title, color=(255, 90, 90), bold=True)
        put(tr + 1, max(1, (width - len(reason_line)) // 2), reason_line, color=(255, 200, 120), bold=True)
        flush()
        time.sleep(0.35)

    for frame in range(frame_count):
        t: float = frame / frame_count
        heli_x: int = int((width + 6) + ((-_HELI_W - 6) - (width + 6)) * t)
        heli_y: int = int(base_y + wave_amp * math.sin(wave_freq * t * math.tau))

        if startup_state is not None and startup_state.failed.is_set():
            _crash_sequence(heli_x, heli_y, startup_state.reason)
            raise RuntimeError(startup_state.reason or "服务启动失败")

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

    startup_hint: str = (
        "  ✦ 服务已就绪, 浏览器即将自动打开"
        if startup_state is not None and startup_state.started.is_set()
        else "  ✦ 服务启动中..."
    )

    info_top: int = sep_row + 2
    info_left: int = max(1, (width - 58) // 2)
    info_lines: list[tuple[str, tuple[int, int, int]]] = [
        (f"  ✦ 端口   │ {port}", theme.acc[0]),
        (f"  ✦ 访问   │ http://localhost:{port}", theme.acc[1 % len(theme.acc)]),
        ("", (0, 0, 0)),
        ("  ✦ GitHub │ https://github.com/Water-Run/MyBiOut", theme.ga),
        ("  ✦ Author │ WaterRun", theme.gb),
        ("", (0, 0, 0)),
        (startup_hint, _lerp(theme.ga, theme.gb, 0.5)),
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

    startup_state: _ServerStartupState = _start_server_in_background(port)
    animation_error: Exception | None = None

    try:
        _play_animation(port, startup_state)
    except Exception as e:
        animation_error = e

    if startup_state.failed.is_set():
        print(_BANNER_FALLBACK)
        print(f"  ✦ 端口: {port}")
        print(f"  ✦ 启动失败: {startup_state.reason or '未知原因'}")
        print("  ✦ 请检查端口占用/配置后重试")
        print()
        return

    if animation_error is not None:
        print(_BANNER_FALLBACK)
        print(f"  ✦ 端口: {port}")
        print(f"  ✦ 访问: http://localhost:{port}")
        print("  ✦ GitHub: https://github.com/Water-Run/MyBiOut")
        print("  ✦ Author: WaterRun")
        print()

    if not _wait_server_startup(startup_state, timeout=25.0):
        print(_BANNER_FALLBACK)
        print(f"  ✦ 端口: {port}")
        print(f"  ✦ 启动失败: {startup_state.reason or '服务启动超时'}")
        print()
        return

    def _open_browser() -> None:
        r"""
        延迟后自动打开浏览器访问地址
        :return: None: 无返回值
        """
        time.sleep(0.35)
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=_open_browser, daemon=True).start()

    try:
        while startup_state.thread is not None and startup_state.thread.is_alive():
            time.sleep(0.2)
    except KeyboardInterrupt:
        if startup_state.server is not None:
            startup_state.server.should_exit = True
        if startup_state.thread is not None:
            startup_state.thread.join(timeout=5.0)


if __name__ == "__main__":
    main()
    