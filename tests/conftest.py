r"""
共享 fixture: 加载打包模块、构造最小可组装目录树。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

根目录 = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def 工程根() -> Path:
    return 根目录


@pytest.fixture
def 打包模块():
    r"""每次测试重新加载 打包.py, 避免改源码后 session 缓存旧代码。"""
    路径 = 根目录 / "打包.py"
    名 = "mybiout_pack_under_test"
    # 清掉旧模块, 保证读到最新磁盘内容
    sys.modules.pop(名, None)
    规格 = importlib.util.spec_from_file_location(名, 路径)
    assert 规格 and 规格.loader
    模块 = importlib.util.module_from_spec(规格)
    sys.modules[名] = 模块
    规格.loader.exec_module(模块)
    return 模块


@pytest.fixture
def 假工具bin(tmp_path: Path) -> Path:
    r"""最小 bin: BBDown.exe + ffmpeg.exe (空文件即可过校验)。"""
    bin目录 = tmp_path / "bin"
    bin目录.mkdir()
    (bin目录 / "BBDown.exe").write_bytes(b"MZ-fake")
    (bin目录 / "ffmpeg.exe").write_bytes(b"MZ-fake")
    return bin目录


@pytest.fixture
def 假构建产物(tmp_path: Path) -> Path:
    r"""模拟 PyInstaller onedir 输出。"""
    出 = tmp_path / "MyBiOut!"
    出.mkdir()
    (出 / "MyBiOut!.exe").write_bytes(b"MZ-fake-exe")
    (出 / "_internal").mkdir()
    (出 / "_internal" / "payload.dat").write_bytes(b"x" * 64)
    (出 / "readme.txt").write_text("hi", encoding="utf-8")
    return 出
