r"""
localout 模块的 ADB 扫描行为单元测试
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from mybiout.pages.localout import localout as lm


def test_parse_ls_output_basic() -> None:
    raw: str = "video.m4s\naudio.m4s\n80\ncover.jpg\n"
    assert lm._parse_ls_output(raw) == ["video.m4s", "audio.m4s", "80", "cover.jpg"]


def test_parse_ls_output_ansi_color() -> None:
    r"""
    模拟某些 Android ROM 默认 ls 含 ANSI 颜色码
    """
    raw: str = "\x1b[0m\x1b[01;34mc_test12345\x1b[0m\n\x1b[01;34mc_noentry\x1b[0m\n"
    assert lm._parse_ls_output(raw) == ["c_test12345", "c_noentry"]


def test_parse_ls_output_filters_dot_ls() -> None:
    raw: str = ".\n..\nfoo\nls: cannot access 'bar': No such file or directory\nbaz\n"
    assert lm._parse_ls_output(raw) == ["foo", "baz"]


def test_parse_ls_output_empty() -> None:
    assert lm._parse_ls_output("") == []
    assert lm._parse_ls_output("   \n\n   \n") == []


def test_find_adb_uses_path(fake_adb_env) -> None:
    r"""
    fake adb 已加入 PATH 首位，应能通过 shutil.which 找到
    """
    adb: str | None = lm._find_adb()
    assert adb is not None
    expected: str = "adb.exe" if sys.platform == "win32" else "adb"
    assert adb == expected


def test_get_adb_devices(fake_adb_env) -> None:
    devices: list[tuple[str, str]] = lm._get_adb_devices()
    assert len(devices) == 1
    serial, display = devices[0]
    assert serial == "emulator-5554"
    assert "MockPixel" in display
    assert "emulator-5554" in display


def test_scan_adb_folder_basic(fake_adb_env) -> None:
    r"""
    扫描 /sdcard/Android/data/tv.danmaku.bili/download/c_test12345/80
    应返回 1 个 VideoCard
    """
    remote: str = "/sdcard/Android/data/tv.danmaku.bili/download/c_test12345/80"
    adb: str = lm._find_adb()
    assert adb is not None
    cards: list[lm.VideoCard] = lm._scan_adb_folder(
        adb, "emulator-5554", remote, "c_test12345", "Mock设备",
    )
    assert len(cards) == 1
    c = cards[0]
    assert c.title == "测试视频标题"
    assert c.bvid == "BV1test12345"
    assert c.up_name == "测试UP主"
    assert c.resolution == "1920×1080"
    assert "1080P" in c.quality
    assert "30fps" in c.quality
    assert c.source_type == "adb"
    assert c.device_serial == "emulator-5554"
    assert c.video_path == f"{remote}/video.m4s"
    assert c.audio_path == f"{remote}/audio.m4s"
    assert c.cover_path != ""
    assert Path(c.cover_path).exists()
    assert c.cover_path.endswith(".jpg")


def test_scan_adb_device_full(fake_adb_env) -> None:
    r"""
    完整 _scan_adb_device 流程：扫描全部包，应包含 c_test12345 与 c_noentry
    """
    cards: list[lm.VideoCard] = lm._scan_adb_device("emulator-5554", "Mock设备")
    titles: list[str] = [c.title for c in cards]
    assert "测试视频标题" in titles
    assert "无 entry.json 视频" in titles


def test_make_adb_card_cover_pulled(fake_adb_env) -> None:
    r"""
    验证封面被拉取并写入本地缓存
    """
    adb: str = lm._find_adb()
    assert adb is not None
    card: lm.VideoCard | None = lm._make_adb_card(
        adb, "emulator-5554",
        "/sdcard/Android/data/tv.danmaku.bili/download/c_test12345/80",
        "c_test12345", "Mock设备",
    )
    assert card is not None
    assert card.cover_path != ""
    p = Path(card.cover_path)
    assert p.exists()
    assert p.stat().st_size > 0


def test_make_adb_card_index_json_used(fake_adb_env) -> None:
    r"""
    当 entry.json 不含分辨率时, index.json 提供 resolution/frame_rate
    """
    adb: str = lm._find_adb()
    assert adb is not None
    card: lm.VideoCard | None = lm._make_adb_card(
        adb, "emulator-5554",
        "/sdcard/Android/data/tv.danmaku.bili/download/c_test12345/80",
        "c_test12345", "Mock设备",
    )
    assert card is not None
    assert card.resolution == "1920×1080"
    assert "30fps" in card.quality


def test_add_source_thread_emits_cards(fake_adb_env) -> None:
    r"""
    end-to-end: add_source("adb", ..., serial=...) 启动扫描线程后,
    等待结束, source_cards 应包含来自 fake adb 的卡片
    """
    res: dict = lm.add_source(
        source_type="adb",
        path="",
        label="Mock设备",
        serial="emulator-5554",
        package="tv.danmaku.bili",
    )
    assert res["ok"] is True
    deadline: float = time.time() + 10.0
    while time.time() < deadline:
        if lm.S.scan_status == "idle" and lm.S.scan_progress >= 1.0:
            break
        time.sleep(0.05)
    assert lm.S.scan_status == "idle"
    assert len(lm.S.source_cards) >= 1
