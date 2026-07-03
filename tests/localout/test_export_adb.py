r"""
localout ADB 导出行为单元测试
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mybiout.pages.localout import localout as lm


def _制作卡片() -> lm.视频卡片:
    return lm.视频卡片(
        标题="导出测试",
        BV号="BV1exp",
        AV号="1700000001",
        UP主名称="导出UP",
        清晰度="1080P 高清",
        分辨率="1920×1080",
        字节数=1024,
        文件夹名="c_exp",
        来源标签="Mock设备",
        来源类型="adb",
        设备序列号="emulator-5554",
        视频路径="/sdcard/Android/data/tv.danmaku.bili/download/c_exp/80/video.m4s",
        音频路径="/sdcard/Android/data/tv.danmaku.bili/download/c_exp/80/audio.m4s",
        封面路径="",
    )


def test_export_adb_pull_and_combine(fake_adb_env, tmp_path: Path, monkeypatch) -> None:
    r"""
    ADB 拉取 + biliffm4s.combine 端到端路径
    mock _ffm4s.combine 以避免依赖真实的 m4s 文件结构
    """
    if not lm._有合并库:
        pytest.skip("biliffm4s 未安装, 跳过端到端导出测试")

    拉取文件列表: list[str] = []

    def 假合并(父目录: str, 输出路径: str) -> bool:
        from pathlib import Path as _P

        d: _P = _P(父目录)
        for 名称 in ("video.m4s", "audio.m4s"):
            文件路径: _P = d / 名称
            if 文件路径.exists():
                拉取文件列表.append(名称)
        _P(输出路径).write_bytes(b"FAKE_MP4_OUTPUT")
        return True

    monkeypatch.setattr(lm._缓存合并库, "combine", 假合并)

    卡片: lm.视频卡片 = _制作卡片()
    输出目录: Path = tmp_path / "out"
    输出目录.mkdir()

    lm._导出单个(卡片, 输出目录)

    输出列表: list[Path] = list(输出目录.glob("*.mp4"))
    assert len(输出列表) == 1
    输出文件: Path = 输出列表[0]
    assert 输出文件.stat().st_size > 0
    assert 卡片.输出路径 == str(输出文件)
    assert "导出测试" in 输出文件.name
    assert 拉取文件列表 == ["video.m4s", "audio.m4s"]


def test_pull_cover_adb_hits_cache(fake_adb_env) -> None:
    r"""
    二次拉取同一封面应命中本地缓存
    """
    ADB路径: str = lm._寻找ADB()
    assert ADB路径 is not None
    远端目录: str = "/sdcard/Android/data/tv.danmaku.bili/download/c_test12345"

    首次结果: str = lm._拉取ADB封面(ADB路径, "emulator-5554", 远端目录, "c_test12345")
    assert 首次结果 != ""
    再次结果: str = lm._拉取ADB封面(ADB路径, "emulator-5554", 远端目录, "c_test12345")
    assert 首次结果 == 再次结果


def test_pull_cover_adb_missing_returns_empty(fake_adb_env) -> None:
    r"""
    远端无封面时返回空串
    """
    ADB路径: str = lm._寻找ADB()
    assert ADB路径 is not None
    结果: str = lm._拉取ADB封面(
        ADB路径,
        "emulator-5554",
        "/sdcard/Android/data/com.bilibili.app.in/download/ghost",
        "ghost",
    )
    assert 结果 == ""
