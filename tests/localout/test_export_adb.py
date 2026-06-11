r"""
localout ADB 导出行为单元测试
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mybiout.pages.localout import localout as lm


def _make_card() -> lm.VideoCard:
    return lm.VideoCard(
        title="导出测试",
        bvid="BV1exp",
        avid="1700000001",
        up_name="导出UP",
        quality="1080P 高清",
        resolution="1920×1080",
        size_bytes=1024,
        folder_name="c_exp",
        source_label="Mock设备",
        source_type="adb",
        device_serial="emulator-5554",
        video_path="/sdcard/Android/data/tv.danmaku.bili/download/c_exp/80/video.m4s",
        audio_path="/sdcard/Android/data/tv.danmaku.bili/download/c_exp/80/audio.m4s",
        cover_path="",
    )


def test_export_adb_pull_and_combine(fake_adb_env, tmp_path: Path, monkeypatch) -> None:
    r"""
    ADB 拉取 + biliffm4s.combine 端到端路径
    mock _ffm4s.combine 以避免依赖真实的 m4s 文件结构
    """
    if not lm._HAS_FFM4S:
        pytest.skip("biliffm4s 未安装, 跳过端到端导出测试")

    pulled_files: list[str] = []

    def fake_combine(parent_dir: str, output: str) -> bool:
        from pathlib import Path as _P

        d: _P = _P(parent_dir)
        for name in ("video.m4s", "audio.m4s"):
            p: _P = d / name
            if p.exists():
                pulled_files.append(name)
        _P(output).write_bytes(b"FAKE_MP4_OUTPUT")
        return True

    monkeypatch.setattr(lm._ffm4s, "combine", fake_combine)

    card: lm.VideoCard = _make_card()
    output_dir: Path = tmp_path / "out"
    output_dir.mkdir()

    lm._export_single(card, output_dir)

    outputs: list[Path] = list(output_dir.glob("*.mp4"))
    assert len(outputs) == 1
    out: Path = outputs[0]
    assert out.stat().st_size > 0
    assert card.output_path == str(out)
    assert "导出测试" in out.name
    assert pulled_files == ["video.m4s", "audio.m4s"]


def test_pull_cover_adb_hits_cache(fake_adb_env) -> None:
    r"""
    二次拉取同一封面应命中本地缓存
    """
    adb: str = lm._find_adb()
    assert adb is not None
    remote_dir: str = "/sdcard/Android/data/tv.danmaku.bili/download/c_test12345"

    first: str = lm._pull_cover_adb(adb, "emulator-5554", remote_dir, "c_test12345")
    assert first != ""
    second: str = lm._pull_cover_adb(adb, "emulator-5554", remote_dir, "c_test12345")
    assert first == second


def test_pull_cover_adb_missing_returns_empty(fake_adb_env) -> None:
    r"""
    远端无封面时返回空串
    """
    adb: str = lm._find_adb()
    assert adb is not None
    result: str = lm._pull_cover_adb(
        adb, "emulator-5554",
        "/sdcard/Android/data/com.bilibili.app.in/download/ghost",
        "ghost",
    )
    assert result == ""
