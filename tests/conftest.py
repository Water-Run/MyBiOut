r"""
测试根 conftest: 为所有测试提供隔离的配置文件, 避免污染用户配置

:file: tests/conftest.py
:author: WaterRun
:time: 2026-07-08
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mybiout.pages import utils as 工具


@pytest.fixture(autouse=True)
def 隔离配置(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    r"""
    将 utils._配置路径 重定向到 tmp_path/config.ini, 防止测试读/写真实 config.ini
    设为 autouse 是为了避免任何测试间相互影响, 也防止误写入用户工作树

    已知问题: mybiout/pages/utils.py 的 ConfigParser(interpolation=None) 严格模式
    会在用户 config.ini 包含非法行 (如空键, 空节名) 时抛 ParsingError.
    本夹具同时确保所有测试在干净配置下运行.
    """
    临时配置: Path = tmp_path / "config.ini"
    原始路径: Path = 工具._配置路径
    monkeypatch.setattr(工具, "_配置路径", 临时配置)
    yield 临时配置
    monkeypatch.setattr(工具, "_配置路径", 原始路径)
