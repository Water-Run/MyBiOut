r"""
发布 RAR 打包脚本的单元测试 (不依赖本机 WinRAR 完成真实压缩)

:file: tests/test_pack_rar.py
:author: WaterRun
:time: 2026-07-17
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

仓库根 = Path(__file__).resolve().parent.parent
脚本路径 = 仓库根 / "scripts" / "pack_rar.py"


def _加载打包模块():
    r"""
    动态加载 scripts/pack_rar.py
    """
    规格 = importlib.util.spec_from_file_location("pack_rar", 脚本路径)
    assert 规格 is not None and 规格.loader is not None
    模块 = importlib.util.module_from_spec(规格)
    规格.loader.exec_module(模块)
    return 模块


def test_打包批处理存在于仓库根() -> None:
    r"""
    发行打包入口 打包.bat 必须在仓库根目录
    """
    批处理 = 仓库根 / "打包.bat"
    assert 批处理.is_file()
    文本 = 批处理.read_text(encoding="utf-8")
    assert "assemble_green.py" in 文本
    assert "pack_rar.py" in 文本
    assert "MyBiOut.spec" in 文本


def test_pack_rar可解析版本号() -> None:
    r"""
    取版本号 必须读到已交付包内 __version__
    """
    模块 = _加载打包模块()
    版本 = 模块.取版本号()
    assert 版本
    from mybiout import __version__

    assert 版本 == __version__


def test_缺少绿色目录时pack_rar失败() -> None:
    r"""
    无 dist/MyBiOut-green 时 主流程 应非零退出
    """
    模块 = _加载打包模块()
    原始 = 模块.绿色目录
    try:
        模块.绿色目录 = 仓库根 / "dist" / "__no_such_green__"
        assert 模块.主流程() != 0
    finally:
        模块.绿色目录 = 原始


def test_无Rar时pack_rar给出明确失败(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    r"""
    绿色目录存在但找不到 Rar.exe 时失败
    """
    模块 = _加载打包模块()
    假绿 = tmp_path / "MyBiOut-green"
    假绿.mkdir()
    (假绿 / "MyBiOut.exe").write_bytes(b"")
    monkeypatch.setattr(模块, "绿色目录", 假绿)
    monkeypatch.setattr(模块, "寻找Rar可执行文件", lambda: None)
    monkeypatch.setattr(模块, "发布目录", tmp_path / "release")
    assert 模块.主流程() == 1
