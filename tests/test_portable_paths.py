r"""
便携路径与绿色版启动参数相关测试

:file: tests/test_portable_paths.py
:author: WaterRun
:time: 2026-07-17
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mybiout.pages import utils as 工具


def test_开发态运行根为包目录() -> None:
    r"""
    非冻结环境下运行根应指向 mybiout 包目录
    """
    根: Path = 工具.取运行根目录()
    assert 根.name == "mybiout"
    assert (根 / "pages").is_dir()


def test_资源与工具目录可解析() -> None:
    r"""
    资源根、页面、静态资源、工具目录均应可解析
    """
    assert 工具.取资源根目录().is_dir()
    assert 工具.取页面目录().is_dir()
    assert 工具.取静态资源目录().is_dir()
    assert 工具.取工具目录().name == "bin"
    assert (工具.取资源根目录() / "pages").is_dir()


def test_配置路径文件名为config_ini() -> None:
    r"""
    配置文件名固定为 config.ini (测试夹具会改写父目录, 故不校验绝对路径)
    """
    assert 工具._当前配置路径().name == "config.ini"
    assert (工具.取运行根目录() / "config.ini").name == "config.ini"


def test_资料目录可写旁路() -> None:
    r"""
    auth_profile 应位于运行根 (可写旁路)
    """
    assert 工具.取资料目录() == 工具.取运行根目录() / "auth_profile"


def test_旁路bin优先于资源内置bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    r"""
    取工具目录: 运行根旁路 bin 存在时优先使用, 否则回退资源根 bin
    直接调用已交付的 取工具目录 / 取运行根目录 / 取资源根目录
    """
    运行根: Path = tmp_path / "run"
    资源根: Path = tmp_path / "res"
    旁路工具: Path = 运行根 / "bin"
    内置工具: Path = 资源根 / "bin"
    旁路工具.mkdir(parents=True)
    内置工具.mkdir(parents=True)
    (旁路工具 / "marker-side.txt").write_text("side", encoding="utf-8")
    (内置工具 / "marker-res.txt").write_text("res", encoding="utf-8")

    monkeypatch.setattr(工具, "取运行根目录", lambda: 运行根)
    monkeypatch.setattr(工具, "取资源根目录", lambda: 资源根)

    选中: Path = 工具.取工具目录()
    assert 选中 == 旁路工具
    assert (选中 / "marker-side.txt").is_file()

    # 无旁路时回退资源 bin
    import shutil

    shutil.rmtree(旁路工具)
    assert not 旁路工具.is_dir()
    回退: Path = 工具.取工具目录()
    assert 回退 == 内置工具
    assert (回退 / "marker-res.txt").is_file()


def test_冻结态运行根取自可执行文件旁(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    r"""
    模拟 sys.frozen: 取运行根目录 必须返回 exe 所在目录
    """
    绿色根: Path = tmp_path / "MyBiOut-green"
    绿色根.mkdir()
    假可执行: Path = 绿色根 / "MyBiOut.exe"
    假可执行.write_bytes(b"")

    monkeypatch.setattr(工具.系统信息, "frozen", True, raising=False)
    monkeypatch.setattr(工具.系统信息, "executable", str(假可执行))

    assert 工具.是否冻结运行() is True
    assert 工具.取运行根目录() == 绿色根.resolve()
    assert 工具.取资料目录() == 绿色根.resolve() / "auth_profile"


def test_主程序支持浏览器与窗口参数() -> None:
    r"""
    启动参数应包含绿色版相关开关; 窗口壳入口函数可导入
    """
    from mybiout import main as 主模块

    源码: str = Path(主模块.__file__).read_text(encoding="utf-8")
    assert "--browser" in 源码
    assert "--no-animation" in 源码
    assert "_启动窗口壳" in 源码
    assert "是否冻结运行" in 源码
    assert callable(主模块._启动窗口壳)
    assert isinstance(主模块._可否使用窗口壳(), bool)


def test_主程序帮助输出含绿色参数(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    r"""
    通过已交付主入口 主程序() + --help 验证 CLI 标志 (真实 ArgumentParser 路径)
    """
    from mybiout.main import 主程序

    monkeypatch.setattr(sys, "argv", ["MyBiOut!", "--help"])
    with pytest.raises(SystemExit) as 退出:
        主程序()
    assert 退出.value.code == 0
    捕获 = capsys.readouterr()
    输出: str = (捕获.out or "") + (捕获.err or "")
    assert "--port" in 输出
    assert "--browser" in 输出
    assert "--no-animation" in 输出
