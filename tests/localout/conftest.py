r"""
为 localout 测试构造:
  1. 样例缓存树 (tests/localout/sample_cache/sdcard/...)
  2. monkeypatch _adb_run 与 _find_adb 指向纯 Python fake adb 逻辑
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from mybiout.pages.localout import localout as lm
from tests.localout import fake_adb

SAMPLE_ROOT: Path = Path(__file__).resolve().parent / "sample_cache"


def _build_sample_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    r"""
    在 tmp_path_factory 下重建样例缓存, 并返回 sdcard 根 (含 Android/data/...)
    """
    src: Path = SAMPLE_ROOT / "sdcard"
    dst: Path = tmp_path_factory.mktemp("sample_cache") / "sdcard"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    download_root: Path = dst / "Android" / "data" / "tv.danmaku.bili" / "download"
    for relative_dir in (
        Path("c_test12345") / "80",
        Path("c_noentry") / "32",
        Path("c_exp") / "80",
    ):
        media_dir: Path = download_root / relative_dir
        media_dir.mkdir(parents=True, exist_ok=True)
        (media_dir / "video.m4s").write_bytes(b"fake video stream")
        (media_dir / "audio.m4s").write_bytes(b"fake audio stream")
    return dst


@pytest.fixture
def fake_adb_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    r"""
    准备 fake adb 运行环境:
      1. 在 tmp_path_factory 下复制样例缓存树
      2. monkeypatch _find_adb 返回固定 bin 名
      3. monkeypatch _adb_run 调用纯 Python fake adb
    返回样例缓存根目录
    """
    sample_root: Path = _build_sample_tree(tmp_path_factory)
    monkeypatch.setenv("MYBIOUT_FAKE_ADB_ROOT", str(sample_root))

    bin_name: str = "adb.exe" if sys.platform == "win32" else "adb"
    monkeypatch.setattr(lm, "_find_adb", lambda: bin_name)

    def _patched_adb_run(adb: str, serial: str, *args: str, timeout: float = 10) -> object:
        argv: list[str] = ["-s", serial, *args]
        return fake_adb.run(argv, sample_root)

    monkeypatch.setattr(lm, "_adb_run", _patched_adb_run)
    return sample_root


@pytest.fixture(autouse=True)
def reset_global_state():
    r"""
    隔离测试之间的 _State 全局对象
    """
    lm.S.source_cards.clear()
    lm.S.task_cards.clear()
    lm.S.completed_cards.clear()
    lm.S.logs.clear()
    lm.S._known_keys.clear()
    lm.S._available_keys.clear()
    lm.S.scan_status = "idle"
    lm.S.export_status = "idle"
    lm.S._scan_cancel.clear()
    lm.S._scan_pause.clear()
    lm.S._export_cancel.clear()
    yield
    lm.S._scan_cancel.clear()
    lm.S._scan_pause.clear()
    lm.S._export_cancel.clear()
