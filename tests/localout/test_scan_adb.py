r"""
localout 模块的 ADB 扫描行为单元测试
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from mybiout.pages.localout import localout as lm


def test_parse_ls_output_basic() -> None:
    原始输出: str = "video.m4s\naudio.m4s\n80\ncover.jpg\n"
    assert lm._解析列表输出(原始输出) == ["video.m4s", "audio.m4s", "80", "cover.jpg"]


def test_parse_ls_output_ansi_color() -> None:
    r"""
    模拟某些 Android ROM 默认 ls 含 ANSI 颜色码
    """
    原始输出: str = "\x1b[0m\x1b[01;34mc_test12345\x1b[0m\n\x1b[01;34mc_noentry\x1b[0m\n"
    assert lm._解析列表输出(原始输出) == ["c_test12345", "c_noentry"]


def test_parse_ls_output_filters_dot_ls() -> None:
    原始输出: str = ".\n..\nfoo\nls: cannot access 'bar': No such file or directory\nbaz\n"
    assert lm._解析列表输出(原始输出) == ["foo", "baz"]


def test_parse_ls_output_empty() -> None:
    assert lm._解析列表输出("") == []
    assert lm._解析列表输出("   \n\n   \n") == []


def test_find_adb_uses_path(fake_adb_env) -> None:
    r"""
    fake adb 已加入 PATH 首位，应能通过 shutil.which 找到
    """
    ADB路径: str | None = lm._寻找ADB()
    assert ADB路径 is not None
    期望值: str = "adb.exe" if sys.platform == "win32" else "adb"
    assert 期望值 == ADB路径


def test_get_adb_devices(fake_adb_env) -> None:
    设备列表: list[tuple[str, str]] = lm._取ADB设备列表()
    assert len(设备列表) == 1
    序列号, 显示名称 = 设备列表[0]
    assert 序列号 == "emulator-5554"
    assert "MockPixel" in 显示名称
    assert "emulator-5554" in 显示名称


def test_scan_adb_folder_basic(fake_adb_env) -> None:
    r"""
    扫描 /sdcard/Android/data/tv.danmaku.bili/download/c_test12345/80
    应返回 1 个视频卡片
    """
    远端路径: str = "/sdcard/Android/data/tv.danmaku.bili/download/c_test12345/80"
    ADB路径: str = lm._寻找ADB()
    assert ADB路径 is not None
    卡片列表: list[lm.视频卡片] = lm._扫描ADB文件夹(
        ADB路径,
        "emulator-5554",
        远端路径,
        "c_test12345",
        "Mock设备",
    )
    assert len(卡片列表) == 1
    卡片项 = 卡片列表[0]
    assert 卡片项.标题 == "测试视频标题"
    assert 卡片项.BV号 == "BV1test12345"
    assert 卡片项.UP主名称 == "测试UP主"
    assert 卡片项.分辨率 == "1920×1080"
    assert "1080P" in 卡片项.清晰度
    assert "30fps" in 卡片项.清晰度
    assert 卡片项.来源类型 == "adb"
    assert 卡片项.设备序列号 == "emulator-5554"
    assert 卡片项.视频路径 == f"{远端路径}/video.m4s"
    assert 卡片项.音频路径 == f"{远端路径}/audio.m4s"
    assert 卡片项.封面路径 != ""
    assert Path(卡片项.封面路径).exists()
    assert 卡片项.封面路径.endswith(".jpg")


def test_scan_adb_device_full(fake_adb_env) -> None:
    r"""
    完整 _扫描ADB设备 流程：扫描全部包，应包含 c_test12345 与 c_noentry
    """
    卡片列表: list[lm.视频卡片] = lm._扫描ADB设备("emulator-5554", "Mock设备")
    标题列表: list[str] = [卡片项.标题 for 卡片项 in 卡片列表]
    assert "测试视频标题" in 标题列表
    assert "无 entry.json 视频" in 标题列表


def test_add_source_rejects_missing_non_adb_path(tmp_path: Path) -> None:
    r"""
    非 ADB 扫描源必须有实际目录，避免空路径或坏路径误扫当前工作目录。
    """
    缺失路径: Path = tmp_path / "missing-cache"

    结果: dict = lm.添加来源(
        来源类型="pc",
        路径文本=str(缺失路径),
        标签="不存在的 PC 缓存",
    )

    assert 结果["ok"] is False
    assert "路径不存在" in str(结果["error"])
    assert lm.状态.扫描状态 == "idle"


def test_add_source_respects_requested_adb_package(fake_adb_env) -> None:
    r"""
    指定 ADB 包名时只扫描该包；fake 样例只包含 tv.danmaku.bili，
    因此扫描国际版包应找不到视频。
    """
    结果: dict = lm.添加来源(
        来源类型="adb",
        路径文本="",
        标签="Mock设备 · 国际版",
        序列号="emulator-5554",
        包名="com.bilibili.app.in",
    )

    assert 结果["ok"] is True
    截止时间: float = time.time() + 10.0
    while time.time() < 截止时间:
        if lm.状态.扫描状态 == "idle" and lm.状态.扫描进度 >= 1.0:
            break
        time.sleep(0.05)

    assert lm.状态.扫描状态 == "idle"
    assert lm.状态.来源卡片列表 == []


def test_make_adb_card_cover_pulled(fake_adb_env) -> None:
    r"""
    验证封面被拉取并写入本地缓存
    """
    ADB路径: str = lm._寻找ADB()
    assert ADB路径 is not None
    卡片: lm.视频卡片 | None = lm._制作ADB卡片(
        ADB路径,
        "emulator-5554",
        "/sdcard/Android/data/tv.danmaku.bili/download/c_test12345/80",
        "c_test12345",
        "Mock设备",
    )
    assert 卡片 is not None
    assert 卡片.封面路径 != ""
    文件路径 = Path(卡片.封面路径)
    assert 文件路径.exists()
    assert 文件路径.stat().st_size > 0


def test_make_adb_card_index_json_used(fake_adb_env) -> None:
    r"""
    当 entry.json 不含分辨率时, index.json 提供 resolution/frame_rate
    """
    ADB路径: str = lm._寻找ADB()
    assert ADB路径 is not None
    卡片: lm.视频卡片 | None = lm._制作ADB卡片(
        ADB路径,
        "emulator-5554",
        "/sdcard/Android/data/tv.danmaku.bili/download/c_test12345/80",
        "c_test12345",
        "Mock设备",
    )
    assert 卡片 is not None
    assert 卡片.分辨率 == "1920×1080"
    assert "30fps" in 卡片.清晰度


def test_add_source_thread_emits_cards(fake_adb_env) -> None:
    r"""
    end-to-end: 添加来源("adb", ..., serial=...) 启动扫描线程后,
    等待结束, source_cards 应包含来自 fake adb 的卡片
    """
    结果: dict = lm.添加来源(
        来源类型="adb",
        路径文本="",
        标签="Mock设备",
        序列号="emulator-5554",
        包名="tv.danmaku.bili",
    )
    assert 结果["ok"] is True
    截止时间: float = time.time() + 10.0
    while time.time() < 截止时间:
        if lm.状态.扫描状态 == "idle" and lm.状态.扫描进度 >= 1.0:
            break
        time.sleep(0.05)
    assert lm.状态.扫描状态 == "idle"
    assert len(lm.状态.来源卡片列表) >= 1
